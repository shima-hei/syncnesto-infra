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

variable "demo_runtime_enabled" {
  description = "Add dedicated demo connections without replacing normal connections."
  type        = bool
  default     = false
}

variable "demo_database_url" {
  type      = string
  sensitive = true
  ephemeral = true
  default   = ""
  validation {
    condition     = !var.demo_runtime_enabled || (startswith(var.demo_database_url, "postgresql://syncnesto_app:") && endswith(var.demo_database_url, "?sslmode=verify-full"))
    error_message = "Demo runtime requires a restricted URI with verified TLS."
  }
}

variable "demo_secret_key" {
  type      = string
  sensitive = true
  ephemeral = true
  default   = ""
  validation {
    condition     = !var.demo_runtime_enabled || length(var.demo_secret_key) >= 32
    error_message = "Demo JWT signing key must have at least 32 characters."
  }
}

variable "demo_storage_access_key" {
  type      = string
  sensitive = true
  ephemeral = true
  default   = ""
}

variable "demo_storage_secret_key" {
  type      = string
  sensitive = true
  ephemeral = true
  default   = ""
}

variable "demo_supabase_project_ref" {
  type    = string
  default = "jxtwcdmaooiasodubofu"
  validation {
    condition     = can(regex("^[a-z]{20}$", var.demo_supabase_project_ref)) && var.demo_supabase_project_ref != var.supabase_project_ref
    error_message = "Demo Storage must use a separate Supabase Project."
  }
}
