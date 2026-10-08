# Neon APIで作成したロールは管理権限を持つため、実行用ロールはSQLで作る。
provider "postgresql" {
  host             = var.database_host
  database         = var.database_name
  username         = var.database_owner
  password         = var.database_owner_password
  sslmode          = "verify-full"
  superuser        = false
  expected_version = "17.0.0"
  connect_timeout  = 15
  max_connections  = 2
}

resource "random_password" "application" {
  length  = 48
  special = false
}

resource "postgresql_role" "application" {
  name                      = "syncnesto_app"
  login                     = true
  password_wo               = random_password.application.result
  password_wo_version       = "1"
  superuser                 = false
  create_database           = false
  create_role               = false
  replication               = false
  bypass_row_level_security = false
  inherit                   = false
  roles                     = []
  connection_limit          = 20
  statement_timeout         = 30000

  lifecycle {
    prevent_destroy = true
  }
}

resource "postgresql_grant" "public_database" {
  database    = var.database_name
  role        = "public"
  object_type = "database"
  privileges  = []
}

resource "postgresql_grant" "public_schema" {
  database    = var.database_name
  role        = "public"
  schema      = "public"
  object_type = "schema"
  privileges  = ["USAGE"]
}

resource "postgresql_grant" "application_database" {
  database    = var.database_name
  role        = postgresql_role.application.name
  object_type = "database"
  privileges  = ["CONNECT"]
}

resource "postgresql_grant" "application_schema" {
  database    = var.database_name
  role        = postgresql_role.application.name
  schema      = "public"
  object_type = "schema"
  privileges  = ["USAGE"]
}

locals {
  application_privileges = {
    table    = ["SELECT", "INSERT", "UPDATE", "DELETE"]
    sequence = ["USAGE", "SELECT"]
  }
}

resource "postgresql_grant" "application_objects" {
  for_each = local.application_privileges

  database    = var.database_name
  role        = postgresql_role.application.name
  schema      = "public"
  object_type = each.key
  privileges  = each.value
}

resource "postgresql_default_privileges" "application_objects" {
  for_each = local.application_privileges

  database    = var.database_name
  role        = postgresql_role.application.name
  owner       = var.database_owner
  schema      = "public"
  object_type = each.key
  privileges  = each.value
}
