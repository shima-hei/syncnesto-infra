mock_provider "postgresql" {}
mock_provider "random" {}

variables {
  database_host            = "ep-demo.neon.tech"
  pooled_host              = "ep-demo-pooler.neon.tech"
  production_database_host = "ep-existing.neon.tech"
  database_name            = "syncnesto"
  database_owner           = "syncnesto_owner"
  database_owner_password  = "fixture-owner-password"
}

run "restricted_runtime_role" {
  command = plan
  assert {
    condition     = !postgresql_role.application.superuser && !postgresql_role.application.create_database && !postgresql_role.application.create_role && !postgresql_role.application.replication && !postgresql_role.application.bypass_row_level_security && !postgresql_role.application.inherit && length(postgresql_role.application.roles) == 0
    error_message = "Demo runtime must have no administration or inherited privileges."
  }
  assert {
    condition     = postgresql_grant.application_database.privileges == toset(["CONNECT"]) && length(postgresql_grant.public_database.privileges) == 0 && postgresql_default_privileges.application_objects["table"].privileges == toset(["SELECT", "INSERT", "UPDATE", "DELETE"])
    error_message = "Only required current and future object privileges may be granted."
  }
}

run "reject_existing_database" {
  command = plan
  variables {
    production_database_host = "ep-demo.neon.tech"
  }
  expect_failures = [var.database_host]
}

run "reject_mismatched_pooler" {
  command = plan
  variables {
    pooled_host = "ep-existing-pooler.neon.tech"
  }
  expect_failures = [var.pooled_host]
}

run "reject_state_database" {
  command = plan
  variables {
    database_name = "syncnesto_terraform"
  }
  expect_failures = [var.database_name]
}
