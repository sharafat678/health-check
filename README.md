# **AWS Cost Optimization - Health Check Project**  

## **Overview**  
This project is designed to **reduce AWS costs** by identifying and managing **unused AWS resources**. The AWS Lambda function checks the following resources and sends a report via **Amazon SNS** to the responsible person's email.  

## **Resources Monitored**  
1. **Snapshots** - Identifies snapshots older than 30 days.  
2. **Unused Volumes** - Finds EBS volumes that have been **unused for over 30 days**.  
3. **Load Balancers Without Registered Targets** - Detects ELBs that are not actively serving traffic.  
4. **Unattached Elastic IPs** - Identifies EIPs that are not attached to any running EC2 instance.  
5. **Stopped EC2 Instances** - Finds EC2 instances that have been **stopped for over 30 days**.  
6. **Unused S3 Buckets** - Detects **empty S3 buckets** or those that haven't been accessed in **30+ days**.  

At the end of the execution, the Lambda function **sends an email notification** with the report.

---

## **Implementation Steps** 

## **Pre-requisites** 

✅ **Steps to create the IAM Role:**  

## **1️⃣ Create IAM Role for Lambda**  
```sh
aws iam create-role --role-name AWSHealthCheckRole \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
      {
        "Effect": "Allow",
        "Principal": { "Service": "lambda.amazonaws.com" },
        "Action": "sts:AssumeRole"
      }
    ]
  }'
```

✅ **Attach Policy to Role**  
```sh
aws iam put-role-policy --role-name AWSHealthCheckRole \
  --policy-name AWSHealthCheckPolicy \
  --policy-document '{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "ec2:DescribeImages",
                "ec2:DeleteVolume",
                "cloudtrail:LookupEvents",
                "ec2:DeregisterImage",
                "ec2:DescribeInstances",
                "ec2:DescribeVolumeStatus",
                "ec2:DeleteSnapshot",
                "ec2:DescribeVolumes",
                "autoscaling:DescribeLoadBalancerTargetGroups",
                "ec2:DescribeSnapshots",
                "autoscaling:DescribeLoadBalancers",
                "ec2:DescribeVolumeAttribute",
                "elasticloadbalancing:DescribeLoadBalancers",
                "elasticloadbalancing:DescribeTargetGroups",
                "elasticloadbalancing:DescribeTargetHealth",
                "s3:ListAllMyBuckets",
                "s3:ListBucket",
                "ec2:DescribeAddresses",
                "ec2:DescribeNatGateways",
                "sns:Publish"
            ],
            "Resource": "*"
        }
    ]
  }'
```

To allow Lambda to write logs to CloudWatch, attach the AWS-managed policy:

```bash
aws iam attach-role-policy \
    --role-name AWSHealthCheckRole \
    --policy-arn arn:aws-cn:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole   # Replace the correct arn of lambda-execution role policy.
```
---
## **2️⃣ Create SNS Topic & Subscription**  
✅ **Create SNS Topic**  
```sh
SNS_TOPIC_ARN=$(aws sns create-topic --name aws-health-check --query 'TopicArn' --output text)
echo "SNS Topic ARN: $SNS_TOPIC_ARN"
```

✅ **Subscribe Email to SNS Topic**  
change your email address.
```sh
aws sns subscribe --topic-arn $SNS_TOPIC_ARN --protocol email --notification-endpoint your-email@example.com
```
👉 **Check your email** and confirm the AWS SNS subscription.
---

## **3️⃣ Create Lambda Function**  

```bash
wget https://github.com/sharafat678/health-check/blob/main/lambda_function.py
```

✅ **Update Lambda Function to use SNS ARN**
Update your lambda function present in the repo with SNS topic ARN

Run zip command inside the directory where lambda_funtion.py is located.

```bash
zip lambda_function.zip lambda_function.py
```

✅ **Get Role ARN**  
```sh
ROLE_ARN=$(aws iam get-role --role-name AWSHealthCheckRole --query 'Role.Arn' --output text)
```

✅ **Create Lambda Function**  
```sh

aws lambda create-function --function-name AWS-HealthCheck \
    --runtime python3.11 \
    --role $ROLE_ARN \
    --handler lambda_function.lambda_handler \
    --timeout 180 \
    --memory-size 256 \
    --zip-file fileb://lambda_function.zip 

```
(Ensure `lambda_function.zip` contains `lambda_function.py`.)

---


## **4️⃣ Create EventBridge Rule for Scheduled Execution**  
✅ **Create Event Rule to Run Every 2 Weeks**  
```sh
aws events put-rule --name aws-health-check-trigger \
  --schedule-expression "rate(14 days)"
```

✅ **Add Lambda as a Target for the Rule**  
```sh
aws events put-targets --rule aws-health-check-trigger \
  --targets "Id"="1","Arn"="$(aws lambda get-function --function-name AWS-HealthCheck --query 'Configuration.FunctionArn' --output text)"
```

✅ **Grant EventBridge Permission to Invoke Lambda**  
```sh
aws lambda add-permission --function-name AWS-HealthCheck \
  --statement-id EventBridgeInvoke \
  --action "lambda:InvokeFunction" \
  --principal events.amazonaws.com \
  --source-arn "$(aws events describe-rule --name aws-health-check-trigger --query 'Arn' --output text)"
```

---

## **✅ Done!**
🚀 Now your Lambda function will automatically run **every 2 weeks** and send AWS health reports via **SNS email notifications**.

---

## **Expected Email Report Example**

```
Subject: AWS Health Check Report

{
  "UnattachedNATGateways": [],
  "UnattachedElasticIPs": [],
  "stopped-instances": [],
  "s3-buckets": [
    {
      "BucketName": "unused-bucket",
      "Status": "No objects in the bucket"
    }
  ],
  "loadbalancer-without-target": [],
  "unused-volumes": [],
  "unused-snapshots": []
}
```

---

## **Benefits of This Project**  
✅ **Reduces AWS Costs** by identifying & deleting unused resources  
✅ **Prevents unnecessary billing** (e.g., unattached EIPs, unused EBS volumes)  
✅ **Automates monitoring** with Lambda & EventBridge  
✅ **Sends reports directly to email** for quick review  

---

## **Next Steps & Enhancements**
🔹 Add **automatic deletion** of unused resources after approval  
🔹 Integrate **Slack notifications** for real-time alerts  
🔹 Extend monitoring to **RDS, Lambda, and CloudFront**  

---

## **Conclusion**
This AWS Lambda project **automates cost monitoring**, helping AWS users optimize their spending by detecting and reporting unused resources. 🚀  
