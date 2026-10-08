variable "database_host" {
  type = string
  validation {
    condition     = var.database_host != var.production_database_host && endswith(var.database_host, ".neon.tech") && !strcontains(var.database_host, "-pooler")
    error_message = "Use a dedicated direct Neon host, never the existing production host."
  }
}
variable "pooled_host" {
  type = string
  validation {
    condition     = var.pooled_host == replace(var.database_host, "/^([^.]+)\\./", "$1-pooler.")
    error_message = "Use the pooler belonging to the dedicated direct Neon host."
  }
}
variable "database_name" {
  type = string
  validation {
    condition     = var.database_name == "syncnesto"
    error_message = "Use the dedicated syncnesto database, never the Terraform state database."
  }
}
variable "database_owner" {
  type = string
  validation {
    condition     = var.database_owner == "syncnesto_owner"
    error_message = "Use the dedicated migration owner."
  }
}
variable "database_owner_password" {
  type      = string
  sensitive = true
  ephemeral = true
}
