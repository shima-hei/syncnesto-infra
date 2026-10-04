terraform {
  backend "pg" {
    schema_name = "portfolio_state"
  }
}
