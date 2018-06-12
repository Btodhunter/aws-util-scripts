#!/usr/bin/python
"""
Multi-threaded script for assuming the identity of another AWS account and copying all the objects from a bucket in
that account to a bucket in current account. Must be run on a system with valid credentials for destination bucket account.
"""
import boto3
from botocore import exceptions
from Queue import Queue, Empty
from threading import Thread, active_count
from datetime import datetime, date
from pytz import utc
from sys import stdout
from os import path, environ, _exit
from time import sleep

# Constants
assume_role_arn =
assume_role_session = "assumed-s3-archiver-role"
source_bucket_name =
destination_bucket_name =
worker_threads = 100
todays_date = str(date.today())
bucket_prefixes = []

# Set trusted CA cert environment variable for the requests python module (work around SSL error caused by bug in boto3)
#environ['REQUESTS_CA_BUNDLE'] = path.join('/etc/ssl/certs/', 'ca-bundle.crt')


def main():
    """
    Starts the copy s3 bucket job and ensures all daemon threads get shutdown gracefully.
    """
    S3.copy_files(source_bucket_name, destination_bucket_name, threads=worker_threads)

    # Wait for all threads (excluding main) to gracefully shutdown.
    while True:
        if active_count() <= 1:
            stdout.write("All threads closed successfully, exiting script.\n")
            exit(0)


def assume_role(role_arn, session_name):
    """
    Used to assume a role in another AWS account.

    :param role_arn: AWS arn of the assumed role.
    :param session_name: Arbitrary session name, used to identify session in CloudWatch logs.
    :return: Assumed role credentials dict('AccessKeyId', 'SecretAccessKey', 'SessionToken', 'Expiration')
    """
    stdout.write("Assuming Role: " + role_arn + "\n")
    sts_client = boto3.client('sts')

    return sts_client.assume_role(RoleArn=role_arn,
                                  RoleSessionName=session_name)['Credentials']


class CopyWorker(Thread):
    """
    Used to create threads and copy items between s3 buckets. Also manages the boto3 session used to perform the
    s3 copy API call. Inherited from Threading.Thread.

    :param key_queue: Instance of the Queue class which holds all the source bucket keys.
    :param cred_queue: Intance of the Queue class which holds the assumed role credentials.
    :param src_bucket_name: Name of source S3 bucket.
    :param dst_bucket_name: Name of the destination S3 bucket.
    """
    def __init__(self, key_queue, cred_queue, src_bucket_name, dst_bucket_name):
        self._key_queue = key_queue
        self._src_bucket_name = src_bucket_name
        self._dst_bucket_name = dst_bucket_name
        self._cred_queue = cred_queue
        self._session = boto3.session.Session()

        # Call to the Threading.Thread constructor (required to initialize threads properly)
        super(CopyWorker, self).__init__()

    def run(self):
        """
        Copies items between buckets, renews the assumed role credentials if they have expired. Runs indefinitely until
        main thread exits. Overrides the Threading.Thread.run() function.

        :return: None
        """
        # Put thread to sleep for 60 seconds will remaining threads are created
        stdout.write(self.name + " created. Sleeping for 60 seconds, waiting for queue to populate with object keys.\n")
        sleep(60)
        s3_session = self.create_s3_session(self._cred_queue, self._session)
        while True:
            try:
                # Get a new key from the key queue. If it takes longer than 60 seconds to get a key, raise the
                # Queue.Empty exception and exit the loop.
                key = self._key_queue.get(timeout=30)
            except Empty:
                stdout.write("Queue Empty, exiting " + self.name + ".\n")
                exit()

            try:
                self.copy_objects(key, s3_session)

            # ClientError exception from Boto3 is raised when assumed role credentials expire and new credentials must
            # be created.
            except exceptions.ClientError:
                assumed_credentials = self._cred_queue.get()
                if self.check_session_expiration(assumed_credentials.get('Expiration')):
                    stdout.write("Credentials Expired\n")
                    # Get new assume role credentials & put them into the credentials queue
                    self._cred_queue.put(assume_role(assume_role_arn, assume_role_session))
                    # Mark old credentials as done so they're removed from credentials queue
                    self._cred_queue.task_done()
                    s3_session = self.create_s3_session(self._cred_queue, self._session)
                    continue

                else:
                    # If credentials are not expired then another thread already assumed the new role. Put new assume
                    # role credentials back into the queue and create a new s3 session.
                    self._cred_queue.put(assumed_credentials)
                    self._cred_queue.task_done()
                    s3_session = self.create_s3_session(self._cred_queue, self._session)
                    continue

            finally:
                # Mark key from queue done and remove it from queue.
                self._key_queue.task_done()

    def copy_objects(self, key, session):
        """
        Copy objects from an AWS S3 bucket to a different bucket. Uses credentials passed from _cred_queue.

        :param key: S3 object key to be copied.
        :param session: Boto3.session.Session() used to for the copy process
        :return: None
        """
    	message = "Copying " + key.key + " from " + self._src_bucket_name + " to " + self._dst_bucket_name + "\n"
        stdout.write(message)
        session.meta.client.copy_object(
            CopySource={
                'Bucket': self._src_bucket_name,
                'Key': key.key,
            },
            Bucket=self._dst_bucket_name,
        	Key=key.key,
        	ACL='bucket-owner-full-control'
        	)

    @staticmethod
    def check_session_expiration(expiry):
        """
        Checks to see if the current assumed role credentials have expired or not.

        :param expiry: The value of the 'Expiration' key from the assumed role credentials.
        :return: True if session has expired, false if it hasn't.
        """
        if datetime.now(utc) >= expiry:
            return True
        else:
            return False

    @staticmethod
    def create_s3_session(cred_queue, session):
        """
        Creates a Boto3 S3 resource using the assume role credentials which are stored in a credentials queue.

        :param cred_queue: Queue.Queue containing a single credential dictionary from the sts assumed role.
        :param session: Boto3.session.sessoin() to create the S3 resource with
        :return: Boto3 S3 resource opened with the assumed role.
        """
        # Get credentials from credential queue.
        credentials = cred_queue.get()
        stdout.write("Creating new S3 session\n")

        # Put credentials back into queue and mark as done to unlock queue for other threads.
        cred_queue.put(credentials)
        cred_queue.task_done()

        return session.resource('s3',
                                aws_access_key_id=credentials['AccessKeyId'],
                                aws_secret_access_key=credentials['SecretAccessKey'],
                                aws_session_token=credentials['SessionToken']
                                )


class S3(object):
    """
    Used to create Boto3 s3 bucket resources and start multi-threaded copies of all objects from source bucket into
    the destination bucket.
    """

    @staticmethod
    def s3_resource():
        """
        Creates a generic Boto3 S3 resource.

        :return: Boto3 s3 resource.
        """
        return boto3.resource('s3')

    @classmethod
    def copy_files(cls, src_bucket_name, dst_bucket_name, threads):
        """
        Creates a queue populated with all objects from a source AWS S3 bucket. Then creates worker threads which are
        used to copy all items in the key queue to another AWS S3 bucket.

        :param src_bucket_name: Destination AWS S3 bucket name
        :param dst_bucket_name: Source AWS S3 bucket Name
        :param threads: Number of worker threads to be utilized.
        :return: None
        """
        src_bucket = cls.bucket(src_bucket_name)
        dst_bucket = cls.bucket(dst_bucket_name)
        # Queue will block when it reaches max size, will continue filling itself as space becomes available
        # Prevents queue from taking up too much space in memory.
        copy_queue = Queue(maxsize=1000)
        # Create credentials queue and populate it with new assumed role credentials.
        assume_cred_queue = Queue()
        assume_cred_queue.put(assume_role(assume_role_arn, assume_role_session))

        # Create number of threads specified by the worker_threads constant variable.
        for thread in range(threads):
            worker = CopyWorker(copy_queue, assume_cred_queue, src_bucket_name, dst_bucket_name)
            # Set threads as daemon threads so they will shutdown automatically when script is killed
            worker.daemon = True
            # Call Threading.Thread.start() on CopyWorker object, this bootstraps the thread and calls CopyWorker.run()
            worker.start()

        # Populate key queue with all keys in the source bucket resource
        for keys in cls.bucket_keys(src_bucket):
            for key in keys:
                copy_queue.put(key)

        # Block until the key queue is empty.
        copy_queue.join()

    @classmethod
    def bucket_keys(cls, bucket):
        """
        Enumerates all objects in an AWS S3 bucket.

        :param bucket: Boto3 S3 bucket resource.
        :return: list(S3 bucket keys[1000])
        """
        keys = []
        # Get all keys from specified bucket and return in 1000 key lists
        for prefix in bucket_prefixes:
            for key in bucket.objects.filter(Prefix=prefix):
                keys.append(key)

                if len(keys) == 1000:
                    yield keys
                    keys = []
        	# When there are no more keys left in bucket.object.filter() return the remaining list of keys
            else:
                yield keys

    @classmethod
    def bucket(cls, bucket_name):
        """
        Creates a Boto3 S3 bucket resource of specified bucket.

        :param bucket_name: AWS S3 bucket name to be fetched as boto3 resource.
        :return: Boto3 S3 resource.
        """
        s3 = cls.s3_resource()
        bucket = s3.Bucket(bucket_name)
        try:
            s3.meta.client.head_bucket(Bucket=bucket.name)
        except exceptions.ClientError as e:
            # If a client error is thrown, then check that it was a 404 error.
            # If it was a 404 error, then the bucket does not exist.
            error_code = int(e.response['Error']['Code'])
            if error_code == 404:
                raise ValueError('{} bucket doesn\'t exist'.format(bucket_name))

        return bucket

if __name__ == '__main__':
    main()
