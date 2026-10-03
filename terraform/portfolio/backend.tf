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
  }
}

locals {
  backend_environment = {
    APP_ENV                     = "production"
    AUTH_COOKIE_SECURE          = "true"
    CSRF_COOKIE_SECURE          = "true"
    ALLOW_BEARER_TOKEN_RESPONSE = "false"
    ALLOW_AUTHORIZATION_HEADER  = "false"
    FILE_UPLOAD_MODE            = "presigned"
    SQL_ECHO                    = "false"
    LOG_FORMAT                  = "json"
    ALLOWED_HOSTS               = join(",", concat(["${var.project_name}-api.vercel.app"], var.backend_allowed_hosts))
  }
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
