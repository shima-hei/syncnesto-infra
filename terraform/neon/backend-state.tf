terraform {
  backend "pg" {
    schema_name = "database_state"
  }
}
