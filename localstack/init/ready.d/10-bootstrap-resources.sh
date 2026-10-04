#!/bin/sh

set -eu

bucket_name="syncnesto-local-app-bucket"
queue_name="syncnesto-local-app-queue"

if ! awslocal s3api head-bucket --bucket "${bucket_name}" >/dev/null 2>&1; then
  awslocal s3api create-bucket \
    --bucket "${bucket_name}" \
    --create-bucket-configuration LocationConstraint=ap-northeast-1
fi

awslocal s3api put-bucket-versioning \
  --bucket "${bucket_name}" \
  --versioning-configuration Status=Enabled

queue_url=$(awslocal sqs create-queue \
  --queue-name "${queue_name}" \
  --query QueueUrl \
  --output text)

awslocal sqs set-queue-attributes \
  --queue-url "${queue_url}" \
  --attributes \
    DelaySeconds=0,MaximumMessageSize=262144,MessageRetentionPeriod=86400,ReceiveMessageWaitTimeSeconds=0,VisibilityTimeout=30

awslocal s3 cp \
  /opt/syncnesto/default-avatar.png \
  "s3://${bucket_name}/default-avatar.png" \
  --content-type image/png \
  --only-show-errors
