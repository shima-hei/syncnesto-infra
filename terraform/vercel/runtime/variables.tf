variable "vercel_team_id" {
  type    = string
  default = "team_WyjvWWMPeMn7kxuteyNsC7EE"
}

variable "backend_project_id" {
  description = "Injected from the Vercel stack by the execution helper."
  type        = string
}

variable "supabase_project_ref" {
  type    = string
  default = "pdyywnoregglnyjlapta"

  validation {
    condition     = can(regex("^[a-z]{20}$", var.supabase_project_ref))
    error_message = "Set a 20-letter Supabase project reference."
  }
}

variable "storage_region" {
  type    = string
  default = "ap-southeast-1"
}

variable "storage_bucket" {
  type    = string
  default = "syncnesto-portfolio"
}

variable "database_url" {
  description = "Restricted application URI, never the migration owner URI."
  type        = string
  sensitive   = true
  ephemeral   = true

  validation {
    condition     = startswith(var.database_url, "postgresql://syncnesto_app:") && endswith(var.database_url, "?sslmode=verify-full")
    error_message = "Use the restricted syncnesto_app URI with sslmode=verify-full."
  }
}

variable "storage_access_key" {
  type      = string
  sensitive = true
  ephemeral = true
}

variable "storage_secret_key" {
  type      = string
  sensitive = true
  ephemeral = true
}

variable "credential_version" {
  description = "Increment when rotating either the DB or S3 credentials."
  type        = number
  default     = 1
}
