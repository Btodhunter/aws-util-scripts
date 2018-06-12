from boto3 import client
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("ami_id", help="The AMI id that you would like to promote.")
parser.add_argument("account_id", help="The account ID you would like to promote the AMI to.")
args = parser.parse_args()

ami_id = str(args.ami_id)
account_id = str(args.account_id)
client = client('ec2')

client.modify_image_attribute(
    ImageId=ami_id,
    OperationType='add',
    LaunchPermission={
        'Add': [
            {
                'UserId': account_id
            }
        ]
    }
)

ami_details = client.describe_images(
    ExecutableUsers=[account_id],
    ImageIds=[ami_id]
)

snapshot_id = ami_details['Images'][0]['BlockDeviceMappings'][0]['Ebs']['SnapshotId']

client.modify_snapshot_attribute(
    CreateVolumePermission={
        'Add':[
            {
                'UserId': account_id
            }
        ]
    },
    OperationType='add',
    SnapshotId=snapshot_id
)

client.create_tags(
    Resources=[
        ami_id
    ],
    Tags=[
        {
            'Key': 'PromotedtoProd',
            'Value': 'true'
        },
    ]
)
