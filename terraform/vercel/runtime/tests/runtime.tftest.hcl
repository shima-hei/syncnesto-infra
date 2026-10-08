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

run "demo_connections_are_additive" {
  command = plan
  variables {
    demo_runtime_enabled    = true
    demo_database_url       = "postgresql://syncnesto_app:test@demo-pooler.example.com/syncnesto?sslmode=verify-full"
    demo_secret_key         = "test-demo-jwt-key-at-least-32-characters"
    demo_storage_access_key = "demo-access"
    demo_storage_secret_key = "demo-secret"
  }
  assert {
    condition     = vercel_project_environment_variable.database.key == "DATABASE_URL" && vercel_project_environment_variable.storage_access_key.key == "AWS_ACCESS_KEY_ID" && local.public_environment.AWS_S3_BUCKET_NAME == "syncnesto-portfolio"
    error_message = "Normal connection keys and storage target must remain unchanged."
  }
  assert {
    condition     = vercel_project_environment_variable.demo_database[0].key == "DEMO_DATABASE_URL" && vercel_project_environment_variable.demo_jwt[0].key == "DEMO_SECRET_KEY" && local.demo_public_environment.DEMO_AWS_S3_BUCKET_NAME == "syncnesto-demo"
    error_message = "Demo must use distinct configuration keys and a dedicated bucket."
  }
  assert {
    condition     = vercel_project_environment_variable.demo_database[0].sensitive && vercel_project_environment_variable.demo_jwt[0].sensitive && vercel_project_environment_variable.demo_storage_access_key[0].sensitive && vercel_project_environment_variable.demo_storage_secret_key[0].sensitive
    error_message = "Demo credentials must remain backend secrets."
  }
}
