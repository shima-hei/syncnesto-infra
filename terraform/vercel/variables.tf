variable "project_name" {
  description = "Existing project name on Vercel and Neon."
  type        = string
  default     = "syncnesto"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,48}[a-z0-9]$", var.project_name))
    error_message = "Use 3..50 lowercase letters, digits, and hyphens; start with a letter and end with a letter or digit."
  }
}

variable "frontend_domain" {
  description = "Production domain assigned to the frontend independently of the project name."
  type        = string
  default     = "syncnesto.vercel.app"
}

variable "backend_domain" {
  description = "Production domain assigned to the backend independently of the project name."
  type        = string
  default     = "syncnesto-api.vercel.app"
}

variable "vercel_team_id" {
  description = "Vercel team ID confirmed through the connected account."
  type        = string

  validation {
    condition     = can(regex("^team_[A-Za-z0-9]+$", var.vercel_team_id))
    error_message = "Set a Vercel team ID beginning with team_."
  }
}

variable "frontend_github_repository" {
  description = "GitHub owner/repository for the Next.js frontend."
  type        = string
  default     = "shima-hei/SyncNesto-frontend"
}

variable "connect_github" {
  description = "Enable automatic production deployments after the backend URL and Vercel environment variables are ready."
  type        = bool
  default     = false
}

variable "backend_api_url" {
  description = "Public HTTPS origin of FastAPI. Set and apply this before enabling connect_github."
  type        = string
  default     = null

  validation {
    condition     = var.backend_api_url == null ? true : can(regex("^https://[A-Za-z0-9.-]+(:[0-9]+)?/?$", var.backend_api_url))
    error_message = "Use an HTTPS origin without credentials, path, query, or fragment."
  }
}

variable "vercel_function_region" {
  description = "Region for the Next.js BFF and FastAPI functions."
  type        = string
  default     = "sin1"
}

variable "backend_allowed_hosts" {
  description = "Additional verified Vercel production aliases for the backend; no wildcards."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for host in var.backend_allowed_hosts : can(regex("^[A-Za-z0-9.-]+$", host)) && !strcontains(host, "*")])
    error_message = "Set explicit hostnames without scheme, path, or wildcards."
  }
}

variable "neon_region_id" {
  description = "Neon database region. Singapore is close to the Vercel functions. Changing it replaces the project."
  type        = string
  default     = "aws-ap-southeast-1"
}

variable "neon_organization_id" {
  description = "Optional Neon organization ID; null uses the API key's default account context."
  type        = string
  default     = null
}
variable "app_env" {
  description = "Application behavior on the Vercel production target; demo is opt-in."
  type        = string
  default     = "production"
  validation {
    condition     = contains(["production", "demo"], var.app_env)
    error_message = "app_env must be production or demo."
  }
}

variable "demo_data_isolated" {
  description = "Confirm runtime DATABASE_URL and private storage bucket are dedicated to the demo."
  type        = bool
  default     = false
}

variable "deleted_data_cleanup_mode" {
  description = "Normal data cleanup: disabled by default; review dry_run before execute."
  type        = string
  default     = "disabled"
  validation {
    condition     = contains(["disabled", "dry_run", "execute"], var.deleted_data_cleanup_mode)
    error_message = "Use disabled, dry_run or execute."
  }
}

variable "deleted_data_cleanup_tenant_ids" {
  description = "Explicit normal tenant IDs permitted for scheduled cleanup."
  type        = list(number)
  default     = []
  validation {
    condition     = length(var.deleted_data_cleanup_tenant_ids) <= 20 && alltrue([for id in var.deleted_data_cleanup_tenant_ids : id >= 1 && id <= 2147483647 && id == floor(id)])
    error_message = "Set at most 20 positive integer tenant IDs."
  }
}

variable "deleted_data_cleanup_limit" {
  description = "Maximum root resources inspected or purged in one scheduled invocation."
  type        = number
  default     = 20
  validation {
    condition     = var.deleted_data_cleanup_limit >= 1 && var.deleted_data_cleanup_limit <= 100 && var.deleted_data_cleanup_limit == floor(var.deleted_data_cleanup_limit)
    error_message = "Set an integer from 1 to 100."
  }
}

variable "deleted_data_cleanup_budget_seconds" {
  description = "Soft time budget; in-flight storage and DB calls may complete after it."
  type        = number
  default     = 20
  validation {
    condition     = var.deleted_data_cleanup_budget_seconds >= 1 && var.deleted_data_cleanup_budget_seconds <= 40 && var.deleted_data_cleanup_budget_seconds == floor(var.deleted_data_cleanup_budget_seconds)
    error_message = "Set an integer from 1 to 40."
  }
}
