mock_provider "vercel" {}

variables {
  backend_project_id = "prj_backend"
  database_url       = "postgresql://syncnesto_app:test@pooler.example.com/syncnesto?sslmode=verify-full"
  storage_access_key = "test-access"
  storage_secret_key = "test-secret"
}

run "private_runtime_configuration" {
  command = plan

  assert {
    condition     = alltrue([for env in vercel_project_environment_variable.public : env.project_id == "prj_backend" && env.target == toset(["production"])])
    error_message = "Runtime configuration must only target the production backend."
  }

  assert {
    condition     = vercel_project_environment_variable.database.sensitive && vercel_project_environment_variable.storage_access_key.sensitive && vercel_project_environment_variable.storage_secret_key.sensitive
    error_message = "All credentials must be Sensitive environment variables."
  }

  assert {
    condition     = !contains(keys(local.public_environment), "DATABASE_URL") && !contains(keys(local.public_environment), "AWS_SECRET_ACCESS_KEY")
    error_message = "Public configuration must not contain credentials."
  }
}

run "reject_owner_database_uri" {
  command = plan

  variables {
    database_url = "postgresql://syncnesto_owner:test@database.example.com/syncnesto?sslmode=verify-full"
  }

  expect_failures = [var.database_url]
}
