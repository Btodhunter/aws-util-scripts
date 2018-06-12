from boto3 import client
import argparse
from time import sleep

parser = argparse.ArgumentParser()
parser.add_argument('stack_name', help='The CloudFormation stack name to check.')
args = parser.parse_args()

cf_stack_name = str(args.stack_name)

cf_client = client('cloudformation')

def main():
    status = get_stack_status(cf_client, cf_stack_name)
    print(status)

    while True:
        if 'UPDATE_IN_PROGRESS' in status:
            sleep(30)
            status = get_stack_status(cf_client, cf_stack_name)

        elif 'UPDATE_COMPLETE' in status:
            print(status)
            break

        else:
            print(status)
            exit(1)


def get_stack_status(client, stack_name):
    return client.describe_stacks(StackName=stack_name)['Stacks'][0]['StackStatus']

if __name__ == "__main__":
    main()
