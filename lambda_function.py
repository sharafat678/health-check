import boto3
import json
from datetime import datetime, timezone, timedelta


sns_client = boto3.client('sns', region_name='cn-northwest-1')  # Change to your AWS region
SNS_TOPIC_ARN = "arn:aws-cn:sns:cn-northwest-1:216962084:aws-health-check"  # Replace with your topic ARN

# Create S3 and CloudTrail clients
s3_client = boto3.client('s3')
cloudtrail_client = boto3.client('cloudtrail')

# Define the threshold for 30 days (ensure it's timezone-aware)
threshold_date = (datetime.utcnow() - timedelta(days=30)).replace(tzinfo=timezone.utc)
# Initialize EC2 client
ec2_client = boto3.client('ec2')
#threshold_date = datetime.now(timezone.utc) - timedelta(days=30)



################  Main ############

def lambda_handler(event, context):
# older snapshots
    snapshots_to_delete = get_snapshots_to_delete()
    
    if snapshots_to_delete:
        print(f"Snapshots to be deleted: {snapshots_to_delete}")
    else:
        print("No snapshots need to be deleted.")
    
# Get the list of un-used volumes

    old_unused_volumes = get_old_unused_volumes()
    
    print("Final List of Old Unused Volumes:", old_unused_volumes)

########## Get the list of load balancers without registered targets
    lb_without_targets = get_loadbalancers_without_targets()
   
########## un-attached nat gateway#########
    unattached_nat_gateways = get_unattached_nat_gateways()

    if not unattached_nat_gateways:
        print("No unattached NAT Gateways found.")
    else:
        print("List of unattached NAT Gateways:")
        for nat in unattached_nat_gateways:
            print(f"NAT Gateway: {nat['NatGatewayId']}, State: {nat['State']}, VPC: {nat['VpcId']}, Subnet: {nat['SubnetId']}")

################## get the un attached elastic-ips #############
    unattached_eips = get_unattached_elastic_ips()

    if not unattached_eips:
        print("No unattached Elastic IPs found.")
    else:
        print("List of unattached Elastic IPs:")
        for eip in unattached_eips:
            print(f"Public IP: {eip['PublicIp']}, Allocation ID: {eip['AllocationId']}")
###################stopped instances#################
    stopped_instances = get_stopped_ec2_instances()

    # Log results
    if not stopped_instances:
        print("No EC2 instances have been stopped for more than 30 days.")
    else:
        print("List of EC2 instances stopped for more than 30 days:")
        for instance in stopped_instances:
            print(f"Instance: {instance['InstanceId']}, Stopped Since: {instance['StoppedSince']}")

################### empty s3 bucket
    unused_buckets = get_unused_s3_buckets()
    
    # If no unused buckets, log a message
    if not unused_buckets:
        print("All buckets are actively being used.")
    else:
        print("List of unused buckets (no objects or no recent access):")
        for bucket in unused_buckets:
            print(f"Bucket: {bucket['BucketName']}, Status: {bucket['Status']}")


    report = {
    "UnattachedNATGateways": unattached_nat_gateways,
    "UnattachedElasticIPs": unattached_eips,
    "stopped-instances": stopped_instances,
    "Unused-s3-buckets": unused_buckets,
    "loadbalancer-without-target": lb_without_targets,
    "Unused-volumes": old_unused_volumes,
    "Unused-snapshots": snapshots_to_delete
    }

    response = send_sns_notification(report)

    return {
        'statusCode': 200,
        'body': json.dumps(report)  # ✅ Ensure JSON format
    }


#################  Functions

###########older snapshots

def send_sns_notification(report_body):
    subject = "AWS Health Check Report"
    message = json.dumps(report_body, indent=2)

    response = sns_client.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=message,
        Subject=subject
    )
    return response

def get_snapshots_to_delete():
    ec2 = boto3.client('ec2')
    snapshots_to_delete = []

    # Get all EBS snapshots owned by the account
    response = ec2.describe_snapshots(OwnerIds=['self'])

    # Get all active EC2 instance IDs
    instances_response = ec2.describe_instances(Filters=[{'Name': 'instance-state-name', 'Values': ['running']}])
    active_instance_ids = set()

    for reservation in instances_response['Reservations']:
        for instance in reservation['Instances']:
            active_instance_ids.add(instance['InstanceId'])

    # Iterate through each snapshot and check if it should be deleted
    for snapshot in response['Snapshots']:
        snapshot_id = snapshot['SnapshotId']
        volume_id = snapshot.get('VolumeId')

        if not volume_id:
            # Mark snapshot for deletion if it's not attached to any volume
            snapshots_to_delete.append(snapshot_id)
        else:
            # Check if the volume still exists
            try:
                volume_response = ec2.describe_volumes(VolumeIds=[volume_id])
                if not volume_response['Volumes'][0]['Attachments']:
                    snapshots_to_delete.append(snapshot_id)
            except ec2.exceptions.ClientError as e:
                if e.response['Error']['Code'] == 'InvalidVolume.NotFound':
                    # The volume associated with the snapshot is not found (it might have been deleted)
                    snapshots_to_delete.append(snapshot_id)

    return snapshots_to_delete

########### un-used volumes
def get_old_unused_volumes():
    
    unused_volumes = []
    old_unused_volumes = []
    
    # Define the 30-day threshold with timezone (UTC)
    #threshold_date = datetime.datetime.utcnow().replace(tzinfo=tz.UTC) - datetime.timedelta(days=30)

    # Get all volumes
    volumes_response = ec2_client.describe_volumes()

    for volume in volumes_response['Volumes']:
        if volume['State'] == 'available':  # Only check unattached volumes
            volume_id = volume['VolumeId']
            last_used_time = None

            # Query CloudTrail for the latest AttachVolume or DetachVolume event
            event_response = cloudtrail_client.lookup_events(
                LookupAttributes=[
                    {'AttributeKey': 'ResourceName', 'AttributeValue': volume_id}
                ],
                MaxResults=10
            )

            if event_response['Events']:
                latest_event = max(event_response['Events'], key=lambda x: x['EventTime'])
                last_used_time = latest_event['EventTime']

                # Convert last_used_time to timezone-aware (UTC)
                if last_used_time.tzinfo is None:
                    last_used_time = last_used_time.replace(tzinfo=tz.UTC)
            else:
                last_used_time = None  # No record of being used

            # Append all unused volumes
            unused_volumes.append({'VolumeId': volume_id, 'LastUsedTime': last_used_time})

            # Filter volumes not used in the last 30 days
            if last_used_time is None or last_used_time < threshold_date:
                old_unused_volumes.append({'VolumeId': volume_id, 'LastUsedTime': last_used_time})
                print(f"Old Unused Volume: {volume_id}, Last Used: {last_used_time}")
         # Strip tzinfo before returning (optional)
    for volume in old_unused_volumes:
        volume['LastUsedTime'] = volume['LastUsedTime'].strftime('%Y-%m-%d %H:%M:%S')  # Format as string

    return old_unused_volumes

####### Load-balancers

def get_loadbalancers_without_targets():
    # Create an ELBv2 client for ALB (Application Load Balancer)
    elbv2_client = boto3.client('elbv2')
    
    # Initialize an empty list to store the load balancers without targets
    loadbalancers_without_targets = []
    
    # Get all load balancers (ALBs)
    response = elbv2_client.describe_load_balancers()
    
    for lb in response['LoadBalancers']:
        lb_arn = lb['LoadBalancerArn']
        lb_name = lb['LoadBalancerName']
        
        # Get the target groups associated with the load balancer
        target_groups_response = elbv2_client.describe_target_groups(
            LoadBalancerArn=lb_arn
        )
        
        # Check if the load balancer has associated target groups
        for target_group in target_groups_response['TargetGroups']:
            target_group_arn = target_group['TargetGroupArn']
            
            # Check if there are registered targets in the target group
            target_health_response = elbv2_client.describe_target_health(
                TargetGroupArn=target_group_arn
            )
            
            # If no targets are registered in the target group, add the LB to the list
            if not target_health_response['TargetHealthDescriptions']:
                loadbalancers_without_targets.append({
                    'LoadBalancerName': lb_name,
                    'LoadBalancerArn': lb_arn
                })
                
    return loadbalancers_without_targets


################un-used s3 buckets

def get_unused_s3_buckets():
    unused_buckets = []
    
    # List all buckets
    response = s3_client.list_buckets()
    
    # Iterate through each bucket
    for bucket in response['Buckets']:
        bucket_name = bucket['Name']
        
        # Check if the bucket has objects
        objects_response = s3_client.list_objects_v2(Bucket=bucket_name)
        
        # If no objects in the bucket
        if 'Contents' not in objects_response:
            unused_buckets.append({'BucketName': bucket_name, 'Status': 'No objects in the bucket'})
            #print(f"Bucket {bucket_name} has no objects.")
            continue
        
        # Check the last access time of objects
        last_access_time = None
        for obj in objects_response['Contents']:
            last_modified = obj['LastModified']  # This is timezone-aware
            
            # Update the last access time if it's older than the current one
            if not last_access_time or last_modified < last_access_time:
                last_access_time = last_modified
        
        # If the last access time of the most recent object is older than 30 days
        if last_access_time and last_access_time < threshold_date:
            unused_buckets.append({'BucketName': bucket_name, 'Status': 'Bucket not accessed since last 30 days'})
            #print(f"Bucket {bucket_name} has not been accessed in the last 30 days.")
    
    return unused_buckets

##################stopped ec2
def get_stopped_ec2_instances():
    stopped_instances = []

    # Describe all stopped instances
    response = ec2_client.describe_instances(
        Filters=[{'Name': 'instance-state-name', 'Values': ['stopped']}]
    )

    # Iterate through instances
    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            state_transition_time = instance.get('StateTransitionReason', "")

            # Ensure the field is not empty and contains expected format
            if state_transition_time and "User initiated" in state_transition_time:
                stop_time_str = state_transition_time.split('(')[-1].strip(')')
                
                try:
                    stop_time = datetime.strptime(stop_time_str, "%Y-%m-%d %H:%M:%S GMT")
                    stop_time = stop_time.replace(tzinfo=timezone.utc)  # Convert to timezone-aware

                    # Check if the instance has been stopped for more than 30 days
                    if stop_time < threshold_date:
                        stopped_instances.append({'InstanceId': instance_id, 'StoppedSince': stop_time.isoformat()})
                        print(f"Instance {instance_id} has been stopped since {stop_time}")
                
                except ValueError:
                    print(f"Skipping instance {instance_id} due to incorrect date format: {stop_time_str}")

    return stopped_instances

def get_unattached_elastic_ips():
    # Get all allocated Elastic IPs
    response = ec2_client.describe_addresses()
    
    unattached_eips = []

    for address in response['Addresses']:
        if 'AssociationId' not in address:
            unattached_eips.append({
                'PublicIp': address['PublicIp'],
                'AllocationId': address['AllocationId']
            })
            print(f"Unattached Elastic IP: {address['PublicIp']} (Allocation ID: {address['AllocationId']})")

    return unattached_eips

def get_unattached_nat_gateways():
    # Get all NAT Gateways
    response = ec2_client.describe_nat_gateways()

    unattached_nat_gateways = []

    for nat_gateway in response['NatGateways']:
        state = nat_gateway['State']
        if state in ['deleted', 'deleting', 'failed']:  # NATs that are not in use
            unattached_nat_gateways.append({
                'NatGatewayId': nat_gateway['NatGatewayId'],
                'State': state,
                'VpcId': nat_gateway['VpcId'],
                'SubnetId': nat_gateway['SubnetId']
            })
            print(f"Unattached NAT Gateway: {nat_gateway['NatGatewayId']} (State: {state})")

    return unattached_nat_gateways