mock_provider "vercel" {}
mock_provider "random" {}

mock_provider "neon" {}

variables {
  vercel_team_id  = "team_test"
  backend_api_url = null
  connect_github  = false
}

run "bootstrap_without_backend" {
  command = plan

  assert {
    condition     = vercel_project.frontend.git_repository == null && !contains(keys(vercel_project_environment_variable.frontend), "API_BASE_URL")
    error_message = "Bootstrap must not connect GitHub or point a deployment at localhost."
  }

  assert {
    condition     = vercel_project.backend.framework == "fastapi" && vercel_project.backend.git_repository == null && vercel_project.backend.resource_config.fluid && vercel_project.backend.resource_config.function_default_timeout == 60
    error_message = "FastAPI bootstrap must remain disconnected with Fluid Compute and a bounded timeout."
  }
  assert {
    condition     = nonsensitive(vercel_project_environment_variable.backend_public["DELETED_DATA_CLEANUP_MODE"].value) == "disabled" && nonsensitive(vercel_project_environment_variable.backend_public["DELETED_DATA_CLEANUP_TENANT_IDS"].value) == ""
    error_message = "Normal data cleanup must remain disabled until tenant IDs are explicitly reviewed."
  }
}

run "connect_ready_backend" {
  command = plan

  variables {
    connect_github  = true
    backend_api_url = "https://syncnesto-example.vercel.app"
  }

  assert {
    condition     = vercel_project.frontend.git_repository.repo == "shima-hei/SyncNesto-frontend" && nonsensitive(vercel_project_environment_variable.frontend["API_BASE_URL"].value) == "https://syncnesto-example.vercel.app"
    error_message = "The connected production project must use the configured FastAPI origin."
  }

  assert {
    condition     = !contains(keys(vercel_project_environment_variable.frontend), "DATABASE_URL") && vercel_project.frontend.preview_deployments_disabled
    error_message = "Database credentials must stay on the backend and preview must not share the production API."
  }
}

run "reject_connection_without_backend" {
  command = plan

  variables {
    connect_github = true
  }

  expect_failures = [vercel_project.frontend]
}

run "reject_local_backend" {
  command = plan

  variables {
    backend_api_url = "http://localhost:8000"
  }

  expect_failures = [var.backend_api_url]
}

run "reject_wildcard_backend_host" {
  command = plan

  variables {
    backend_allowed_hosts = ["*.vercel.app"]
  }

  expect_failures = [var.backend_allowed_hosts]
}
run "reject_demo_with_shared_data" {
  command = plan
  variables {
    app_env = "demo"
  }
  expect_failures = [vercel_project.backend]
}

run "explicit_isolated_demo" {
  command = plan
  variables {
    app_env            = "demo"
    demo_data_isolated = true
  }
  assert {
    condition     = nonsensitive(vercel_project_environment_variable.backend_public["APP_ENV"].value) == "demo" && nonsensitive(vercel_project_environment_variable.frontend["APP_ENV"].value) == "demo"
    error_message = "Demo behavior must agree on frontend and backend."
  }
  assert {
    condition     = vercel_project_environment_variable.demo_cron_secret.sensitive && vercel_project_environment_variable.demo_cron_secret.key == "CRON_SECRET"
    error_message = "Cleanup credentials must only be installed as a backend secret."
  }
}

run "explicit_normal_cleanup_dry_run" {
  command = plan
  variables {
    deleted_data_cleanup_mode       = "dry_run"
    deleted_data_cleanup_tenant_ids = [1, 7]
  }
  assert {
    condition     = nonsensitive(vercel_project_environment_variable.backend_public["DELETED_DATA_CLEANUP_MODE"].value) == "dry_run" && nonsensitive(vercel_project_environment_variable.backend_public["DELETED_DATA_CLEANUP_TENANT_IDS"].value) == "1,7"
    error_message = "The backend must receive only the explicitly selected normal tenants."
  }
  assert {
    condition     = !contains(keys(vercel_project_environment_variable.frontend), "DELETED_DATA_CLEANUP_MODE") && !contains(keys(vercel_project_environment_variable.frontend), "CRON_SECRET")
    error_message = "Cleanup authorization and settings must stay backend-only."
  }
}

run "reject_cleanup_without_tenants" {
  command = plan
  variables {
    deleted_data_cleanup_mode = "execute"
  }
  expect_failures = [vercel_project.backend]
}

run "reject_cleanup_in_demo" {
  command = plan
  variables {
    app_env                         = "demo"
    demo_data_isolated              = true
    deleted_data_cleanup_mode       = "execute"
    deleted_data_cleanup_tenant_ids = [1]
  }
  expect_failures = [vercel_project.backend]
}

run "reject_invalid_cleanup_tenant_id" {
  command = plan
  variables {
    deleted_data_cleanup_tenant_ids = [0]
  }
  expect_failures = [var.deleted_data_cleanup_tenant_ids]
}
