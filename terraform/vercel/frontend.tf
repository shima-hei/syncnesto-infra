resource "vercel_project" "frontend" {
  name                         = var.project_name
  framework                    = "nextjs"
  node_version                 = "22.x"
  build_command                = "npm run build"
  install_command              = "npm ci"
  preview_deployments_disabled = true
  on_demand_concurrent_builds  = false

  git_repository = var.connect_github ? {
    type              = "github"
    repo              = var.frontend_github_repository
    production_branch = "main"
  } : null

  resource_config = {
    function_default_regions = [var.vercel_function_region]
  }

  vercel_authentication = {
    deployment_type = "only_preview_deployments"
  }

  lifecycle {
    prevent_destroy = true

    precondition {
      condition     = !var.connect_github || var.backend_api_url != null
      error_message = "Set and apply backend_api_url before connecting GitHub."
    }
  }
}

resource "vercel_project_domain" "frontend" {
  project_id = vercel_project.frontend.id
  domain     = var.frontend_domain
}

locals {
  frontend_environment = merge(
    {
      NEXT_PUBLIC_API_BASE_URL = "/api"
      APP_ENV                  = var.app_env
      AUTH_COOKIE_NAME         = "access_token"
      CSRF_COOKIE_NAME         = "csrf_token"
    },
    var.backend_api_url == null ? {} : { API_BASE_URL = var.backend_api_url }
  )
}

resource "vercel_project_environment_variable" "frontend" {
  for_each = local.frontend_environment

  project_id = vercel_project.frontend.id
  key        = each.key
  value      = each.value
  target     = ["production"]
  sensitive  = false
}

resource "random_password" "bff_secret" {
  length  = 48
  special = false
}

resource "vercel_project_environment_variable" "bff_secret" {
  project_id       = vercel_project.frontend.id
  key              = "BFF_SHARED_SECRET"
  value_wo         = random_password.bff_secret.result
  value_wo_version = 1
  target           = ["production"]
  sensitive        = true
}
