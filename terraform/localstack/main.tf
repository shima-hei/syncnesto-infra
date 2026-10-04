locals {
  name_prefix = "${var.project_name}-local"
}

resource "aws_s3_bucket" "app" {
  bucket = "${local.name_prefix}-app-bucket"
}

resource "aws_s3_bucket_versioning" "app" {
  bucket = aws_s3_bucket.app.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_sqs_queue" "app" {
  name                       = "${local.name_prefix}-app-queue"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 86400
}
