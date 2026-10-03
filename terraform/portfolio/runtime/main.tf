terraform {
  required_version = ">= 1.14.0, < 2.0.0"

  required_providers {
    vercel = {
      source  = "vercel/vercel"
      version = "~> 5.19.0"
    }
  }
}

provider "vercel" {
  team = var.vercel_team_id
}

locals {
  public_environment = {
    AWS_REGION                           = var.storage_region
    AWS_S3_BUCKET_NAME                   = var.storage_bucket
    AWS_S3_ENDPOINT_URL                  = "https://${var.supabase_project_ref}.storage.supabase.co/storage/v1/s3"
    AWS_S3_PRESIGNED_URL_EXPIRES_SECONDS = "600"
    FILE_UPLOAD_URL_EXPIRES_SECONDS      = "600"
    AWS_EC2_METADATA_DISABLED            = "true"
  }
}

resource "vercel_project_environment_variable" "public" {
  for_each = local.public_environment

  project_id = var.backend_project_id
  key        = each.key
  value      = each.value
  target     = ["production"]
  sensitive  = false
}

resource "vercel_project_environment_variable" "database" {
  project_id       = var.backend_project_id
  key              = "DATABASE_URL"
  value_wo         = var.database_url
  value_wo_version = var.credential_version
  target           = ["production"]
  sensitive        = true
}

resource "vercel_project_environment_variable" "storage_access_key" {
  project_id       = var.backend_project_id
  key              = "AWS_ACCESS_KEY_ID"
  value_wo         = var.storage_access_key
  value_wo_version = var.credential_version
  target           = ["production"]
  sensitive        = true
}

resource "vercel_project_environment_variable" "storage_secret_key" {
  project_id       = var.backend_project_id
  key              = "AWS_SECRET_ACCESS_KEY"
  value_wo         = var.storage_secret_key
  value_wo_version = var.credential_version
  target           = ["production"]
  sensitive        = true
}
