terraform {
  required_version = ">= 1.14.0, < 2.0.0"
  required_providers {
    neon = {
      source  = "kislerdm/neon"
      version = "~> 0.18.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
  }
  backend "pg" {
    schema_name = "demo_resources_state"
  }
}

variable "free_plan_confirmed" {
  description = "Set only after confirming the selected Neon organization is Free."
  type        = bool
  default     = false
}

resource "neon_project" "demo" {
  name                      = "syncnesto-demo"
  org_id                    = "org-empty-dew-85265327"
  region_id                 = "aws-ap-southeast-1"
  pg_version                = 17
  history_retention_seconds = 21600
  autoscaling_limit_min_cu  = 0.25
  autoscaling_limit_max_cu  = 0.25

  # 新Projectから開始し、既存branchやIdentityをコピーしない。
  branch {
    name          = "production"
    database_name = "syncnesto"
    role_name     = "syncnesto_owner"
  }
  primary_compute {
    name                     = "production"
    autoscaling_limit_min_cu = 0.25
    autoscaling_limit_max_cu = 0.25
  }
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = var.free_plan_confirmed
      error_message = "Confirm the Neon Free plan before provisioning demo resources."
    }
  }
}

resource "random_password" "jwt" {
  length  = 64
  special = false
}
resource "random_password" "bff" {
  length  = 64
  special = false
}
resource "random_password" "cron" {
  length  = 64
  special = false
}

output "neon_project_id" {
  value = neon_project.demo.id
}
output "neon_branch_id" {
  value = neon_project.demo.default_branch_id
}
output "database_admin_connection" {
  value = {
    host        = neon_project.demo.database_host
    pooled_host = neon_project.demo.database_host_pooler
    database    = neon_project.demo.database_name
    username    = neon_project.demo.database_user
    password    = neon_project.demo.database_password
  }
  sensitive = true
}
output "migration_database_url" {
  value     = "postgresql://${neon_project.demo.database_user}:${urlencode(neon_project.demo.database_password)}@${neon_project.demo.database_host}/${neon_project.demo.database_name}?sslmode=verify-full"
  sensitive = true
}
output "backend_jwt_secret" {
  value     = random_password.jwt.result
  sensitive = true
}
output "backend_bff_secret" {
  value     = random_password.bff.result
  sensitive = true
}
output "backend_cron_secret" {
  value     = random_password.cron.result
  sensitive = true
}
