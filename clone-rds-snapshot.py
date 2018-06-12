# Requires an IAM role created on originating AWS account with the following permissions
# "rds:DescribeDBSnapshots","rds:CreateDBSnapshot","rds:DescribeDBInstances",
# "rds:DeleteDBSnapshot","rds:ModifyDBSnapshotAttribute, "sts:*""
#
# Also requires an IAM role created on cloned AWS account with the following permissions
# "rds:DeleteDbInstance", rds:"RestoreDbInstance", rds:"DescribeDBInstances", rds:"ModifyDbInstance"
# This Role will be assumed by the script to create an RDS instance on the cloned AWS account.

from boto3 import client
from time import time, sleep

ASSUME_ROLE_ARN =
EPOC = int(time())
ORIG_AWS_ACCOUNT =
ORIG_DB_INSTANCE_ID =
SNAPSHOT_NAME = ORIG_DB_INSTANCE_ID + '-' + str(EPOC)
CLONE_AWS_ACCOUNT_ID =
CLONE_DB_INSTANCE_ID =
CLONE_MASTER_PASSWORD =

def main():
    prod_rds_client = client('rds')
    assumed_creds = assume_role(ASSUME_ROLE_ARN, 'rds_staging_role')
    assumed_rds_client = client('rds',
        aws_access_key_id=assumed_creds['AccessKeyId'],
        aws_secret_access_key=assumed_creds['SecretAccessKey'],
        aws_session_token=assumed_creds['SessionToken']
    )

    original_instance_details = describe_db_instance(assumed_rds_client, CLONE_DB_INSTANCE_ID)

    create_snapshot(prod_rds_client, SNAPSHOT_NAME, ORIG_DB_INSTANCE_ID)

    if wait_snapshot_status(prod_rds_client, SNAPSHOT_NAME, 'available'):
        share_snapshot(prod_rds_client, SNAPSHOT_NAME, CLONE_AWS_ACCOUNT_ID)

    delete_db_instance(assumed_rds_client, CLONE_DB_INSTANCE_ID)

    if wait_instance_status(assumed_rds_client, CLONE_DB_INSTANCE_ID, 'deleted'):
        snapshot_arn = describe_snapshot(prod_rds_client, SNAPSHOT_NAME)['DBSnapshotArn']
        restore_db_instance(assumed_rds_client, original_instance_details, snapshot_arn)

    if wait_instance_status(assumed_rds_client, CLONE_DB_INSTANCE_ID, 'available', 20):
        change_master_password(assumed_rds_client, CLONE_DB_INSTANCE_ID, CLONE_MASTER_PASSWORD)

    delete_db_snapshot(prod_rds_client, SNAPSHOT_NAME)


def assume_role(role_arn, session_name):
    print('Assuming Role: {}'.format(role_arn))
    sts_client = client('sts')

    creds = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name
    )['Credentials']

    return creds


def change_master_password(client, instance_name, new_password):
    if is_orig(client, instance_name):
        raise ValueError('Do not try to modify production instances!')

    client.modify_db_instance(
        DBInstanceIdentifier=instance_name,
        MasterUserPassword=new_password
    )
    print('Password successfully changed!')
    return


def create_snapshot(client, snapshot_name, instance_id):
    print('Creating snapshot: {}'.format(snapshot_name))
    create_snap = client.create_db_snapshot(
        DBSnapshotIdentifier=snapshot_name,
        DBInstanceIdentifier=instance_id,
        Tags=[
            {'Key' : 'ProductName','Value' : 'brivity'},
            {'Key' : 'ServiceName', 'Value' : 'postgres'}
        ]
    )
    return


def delete_db_instance(client, instance_name):
    if is_orig(client, instance_name):
        raise ValueError('Do not try to modify production instances!')

    print('Deleting instance: {}'.format(instance_name))
    client.delete_db_instance(
        DBInstanceIdentifier=instance_name,
        SkipFinalSnapshot=True
    )
    return


def delete_db_snapshot(client, snapshot_name):
    print('Delting snapshot: {}'.format(snapshot_name))
    client.delete_db_snapshot(
        DBSnapshotIdentifier=snapshot_name
    )
    return


def describe_db_instance(client, instance_name):
    db_instance_details = client.describe_db_instances(
        DBInstanceIdentifier=instance_name
    )

    # Always requests instance details of a single instance which
    # returns a list with a single item.
    return db_instance_details['DBInstances'][0]


def describe_snapshot(client, snapshot_name):
    snap_details = client.describe_db_snapshots(
        DBSnapshotIdentifier=snapshot_name
    )['DBSnapshots']

    # Always requests snapshot details of a single snapshot which
    # returns a list with a single item.
    return snap_details[0]


def is_orig(client, instance_name):
    instance_arn = describe_db_instance(client, instance_name)['DBInstanceArn']

    return ORIG_AWS_ACCOUNT in instance_arn


def restore_db_instance(client, instance_details, snapshot_arn):
    print('Restoring instance: {}'.format(instance_details['DBInstanceIdentifier']))
    client.restore_db_instance_from_db_snapshot(
        DBInstanceIdentifier=instance_details['DBInstanceIdentifier'],
        DBSnapshotIdentifier=snapshot_arn,
        DBInstanceClass=instance_details['DBInstanceClass'],
        DBSubnetGroupName=instance_details['DBSubnetGroup']['DBSubnetGroupName'],
        MultiAZ=False,
        PubliclyAccessible=False,
        AutoMinorVersionUpgrade=True
    )
    return


def share_snapshot(client, snapshot_name, account_id):
    print('Sharing snapshot: {} with account ID: {}'.format(snapshot_name, account_id))
    client.modify_db_snapshot_attribute(
        DBSnapshotIdentifier=snapshot_name,
        AttributeName='restore',
        ValuesToAdd=[account_id]
    )
    return


def wait_instance_status(client, instance_id, status, wait_time=5):
    max_attempts = (wait_time * 2)
    attempts = 0
    while True:
        if attempts > max_attempts:
            raise RuntimeError('Instance did not enter {} status within {} minutes.'.format(status, wait_time))

        try:
            instance_details = describe_db_instance(client, instance_id)
            instance_status = instance_details['DBInstanceStatus']

            if instance_status != status:
                print(instance_status)
                sleep(30)
                attempts += 1
            else:
                print(instance_status)
                return True

        except client.exceptions.DBInstanceNotFoundFault:
            if status == 'deleted':
                print('Instance successfully deleted')
                return True
            else:
                print('Instance does not exist')
                raise


def wait_snapshot_status(client, snapshot_name, status, wait_time=5):
    max_attempts = (wait_time * 2)
    attempts = 0
    while True:
        if attempts > max_attempts:
            raise RuntimeError('Snapshot did not enter {} status within {} minutes'.format(status, wait_time))

        try:
            snap_details = describe_snapshot(client, snapshot_name)
            snap_status = snap_details['Status']

            if snap_status != status:
                print(snap_status)
                sleep(30)
                attempts += 1
            else:
                print(snap_status)
                return True

        except client.exceptions.DBInstanceNotFoundFault:
            if status == 'deleted':
                print('Snapshot successfully deleted')
                return True
            else:
                print('Snapshot does not exist')
                raise


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(error)
        #report_failure(error, REPORTING_SNS_ARN)
