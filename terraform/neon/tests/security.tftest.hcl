mock_provider "postgresql" {}
mock_provider "random" {}

variables {
  database_host           = "db.example.com"
  pooled_host             = "db-pooler.example.com"
  database_name           = "syncnesto"
  database_owner          = "syncnesto_owner"
  database_owner_password = "mock-password"
}

run "least_privilege_application" {
  command = plan
  assert {
    condition = (
      !postgresql_role.application.superuser &&
      !postgresql_role.application.create_database &&
      !postgresql_role.application.create_role &&
      !postgresql_role.application.replication &&
      !postgresql_role.application.bypass_row_level_security &&
      !postgresql_role.application.inherit &&
      length(postgresql_role.application.roles) == 0
    )
    error_message = "Application roles must not have admin privileges or inherit other roles."
  }
  assert {
    condition = (
      toset(postgresql_grant.application_database.privileges) == toset(["CONNECT"]) &&
      toset(postgresql_grant.application_schema.privileges) == toset(["USAGE"]) &&
      toset(postgresql_default_privileges.application_objects["table"].privileges) == toset(["SELECT", "INSERT", "UPDATE", "DELETE"]) &&
      length(postgresql_grant.public_database.privileges) == 0
    )
    error_message = "Grant only data access; PUBLIC must not grant database access or creation."
  }
}
