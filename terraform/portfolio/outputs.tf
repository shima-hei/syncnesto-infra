output "vercel_project_id" {
  description = "Vercel project ID for CLI linking and deployment inspection."
  value       = vercel_project.frontend.id
}

output "vercel_backend_project_id" {
  description = "Vercel project ID for the separate FastAPI deployment."
  value       = vercel_project.backend.id
}

output "backend_jwt_secret" {
  description = "Production JWT signing key, kept separate from the BFF shared key."
  value       = random_password.jwt_secret.result
  sensitive   = true
}

output "neon_project_id" {
  description = "Neon project ID for account inspection and branch management."
  value       = neon_project.portfolio.id
}

output "neon_branch_id" {
  description = "Production branch provisioned with the Neon project."
  value       = neon_project.portfolio.default_branch_id
}

output "database_admin_connection" {
  description = "Admin connection for the separate database-security stack; never pass to the running application."
  value = {
    host        = neon_project.portfolio.database_host
    pooled_host = neon_project.portfolio.database_host_pooler
    database    = neon_project.portfolio.database_name
    username    = neon_project.portfolio.database_user
    password    = neon_project.portfolio.database_password
  }
  sensitive = true
}

output "migration_database_url" {
  description = "Direct DATABASE_URL for Alembic and database backup; contains credentials."
  value       = "postgresql://${neon_project.portfolio.database_user}:${urlencode(neon_project.portfolio.database_password)}@${neon_project.portfolio.database_host}/${neon_project.portfolio.database_name}?sslmode=verify-full"
  sensitive   = true
}

output "backend_bff_secret" {
  description = "BFF_SHARED_SECRET to configure on FastAPI; already stored as a sensitive Vercel production variable."
  value       = random_password.bff_secret.result
  sensitive   = true
}
