mock_provider "vercel" {}
mock_provider "random" {}
mock_provider "neon" {}

variables {
  vercel_team_id = "team_test"
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
}

run "connect_ready_backend" {
  command = plan

  variables {
    connect_github  = true
    backend_api_url = "https://syncnesto-example.onrender.com"
  }

  assert {
    condition     = vercel_project.frontend.git_repository.repo == "shima-hei/SyncNesto-frontend" && nonsensitive(vercel_project_environment_variable.frontend["API_BASE_URL"].value) == "https://syncnesto-example.onrender.com"
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
