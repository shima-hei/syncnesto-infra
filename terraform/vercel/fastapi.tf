resource "vercel_project" "backend" {
  name                                              = "${var.project_name}-api"
  framework                                         = "fastapi"
  preview_deployments_disabled                      = true
  on_demand_concurrent_builds                       = false
  automatically_expose_system_environment_variables = true

  resource_config = {
    function_default_regions = [var.vercel_function_region]
    fluid                    = true
    function_default_timeout = 60
  }

  vercel_authentication = {
    deployment_type = "only_preview_deployments"
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = var.app_env != "demo" || var.demo_data_isolated
      error_message = "Configure a dedicated demo database and private bucket before setting demo_data_isolated=true."
    }
  }
}

resource "vercel_project_domain" "backend" {
  project_id = vercel_project.backend.id
  domain     = var.backend_domain
}

locals {
  backend_environment = merge({
    APP_ENV                     = var.app_env
    DEMO_DATA_ISOLATED          = tostring(var.demo_data_isolated)
    FRONTEND_PUBLIC_URL         = "https://${var.frontend_domain}"
    AUTH_COOKIE_SECURE          = "true"
    CSRF_COOKIE_SECURE          = "true"
    ALLOW_BEARER_TOKEN_RESPONSE = "false"
    ALLOW_AUTHORIZATION_HEADER  = "false"
    FILE_UPLOAD_MODE            = "presigned"
    SQL_ECHO                    = "false"
    LOG_FORMAT                  = "json"
    ALLOWED_HOSTS               = join(",", distinct(concat([var.backend_domain], var.backend_allowed_hosts)))
  }, var.app_env == "demo" ? { EMAIL_PROVIDER = "disabled" } : {})
}

resource "random_password" "demo_cron_secret" {
  length  = 48
  special = false
}

resource "vercel_project_environment_variable" "demo_cron_secret" {
  project_id       = vercel_project.backend.id
  key              = "CRON_SECRET"
  value_wo         = random_password.demo_cron_secret.result
  value_wo_version = 1
  target           = ["production"]
  sensitive        = true
}

resource "vercel_project_environment_variable" "backend_public" {
  for_each = local.backend_environment

  project_id = vercel_project.backend.id
  key        = each.key
  value      = each.value
  target     = ["production"]
  sensitive  = false
}

resource "vercel_project_environment_variable" "backend_bff_secret" {
  project_id       = vercel_project.backend.id
  key              = "BFF_SHARED_SECRET"
  value_wo         = random_password.bff_secret.result
  value_wo_version = 1
  target           = ["production"]
  sensitive        = true
}

resource "random_password" "jwt_secret" {
  length  = 48
  special = false
}

resource "vercel_project_environment_variable" "backend_jwt_secret" {
  project_id       = vercel_project.backend.id
  key              = "SECRET_KEY"
  value_wo         = random_password.jwt_secret.result
  value_wo_version = 1
  target           = ["production"]
  sensitive        = true
}
