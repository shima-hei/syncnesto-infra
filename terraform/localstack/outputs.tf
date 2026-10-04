output "s3_bucket_name" {
  value = aws_s3_bucket.app.bucket
}

output "sqs_queue_name" {
  value = aws_sqs_queue.app.name
}

output "sqs_queue_url" {
  value = aws_sqs_queue.app.url
}
