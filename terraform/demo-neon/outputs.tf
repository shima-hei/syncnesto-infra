output "backend_database_url" {
  description = "Restricted runtime DATABASE_URL; SSL certificate verification is required."
  value       = "postgresql://${postgresql_role.application.name}:${urlencode(random_password.application.result)}@${var.pooled_host}/${var.database_name}?sslmode=verify-full"
  sensitive   = true
}

output "verification_connection" {
  description = "Restricted direct connection used to verify privileges; contains credentials."
  value = {
    host     = var.database_host
    database = var.database_name
    username = postgresql_role.application.name
    password = random_password.application.result
  }
  sensitive = true
}
