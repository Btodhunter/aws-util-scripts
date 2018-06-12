import boto3

def main():
    with open('hostedZones.txt') as zoneFile:
        hostedZones = [line.rstrip('\n') for line in zoneFile]

    with open('resourceRecords.txt') as recordFile:
        resourceRecords = [eval(line) for line in recordFile]

    # print hostedZones
    # print resourceRecords

    zoneIDs = get_zone_ID(hostedZones)

    # print zoneIDs

    for ID in zoneIDs.keys():
        print "creating new record for hosted zone: " + zoneIDs[ID]
        resourceRecords[0]['Name'] = zoneIDs[ID]
        [create_record(ID, record) for record in resourceRecords]


def get_zone_ID(hostedZones):
    r53_client = boto3.client('route53')
    paginator_hostedZones = r53_client.get_paginator('list_hosted_zones')
    response_hostedZones = paginator_hostedZones.paginate()
    allZones = []
    zone_ids = {}

    for response in response_hostedZones:
        allZones = allZones + response['HostedZones']
        #print response

    for zone in allZones:
        if zone['Name'] in hostedZones and zone['Config']['PrivateZone'] == False:
            zone_ids[zone['Id']] = zone['Name']

    return zone_ids


def create_record(hostedZoneID, record_set):
    r53_client = boto3.client('route53')
    r53_client.change_resource_record_sets(
        HostedZoneId=hostedZoneID,
        ChangeBatch={
            'Changes': [
                {
                'Action': 'UPSERT',
                'ResourceRecordSet': record_set
                }
            ]
        }
    )


main()
