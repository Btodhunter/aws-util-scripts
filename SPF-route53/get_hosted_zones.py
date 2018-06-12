import boto3

def main():
    r53_client = boto3.client('route53')
    paginator_hostedZones = r53_client.get_paginator('list_hosted_zones')
    response_hostedZones = paginator_hostedZones.paginate()
    allZones = []

    for response in response_hostedZones:
        allZones = allZones + response['HostedZones']
        #print response

    for zone in allZones:
        print zone['Name']

main()