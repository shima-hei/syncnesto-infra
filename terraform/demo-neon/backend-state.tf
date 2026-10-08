terraform {
  backend "pg" {
    schema_name = "demo_database_state"
  }
}
