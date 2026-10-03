variable "project_name" {
  description = "Name of the portfolio projects on Vercel and Neon."
  type        = string
  default     = "syncnesto-portfolio"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,48}[a-z0-9]$", var.project_name))
    error_message = "Use 3..50 lowercase letters, digits, and hyphens; start with a letter and end with a letter or digit."
  }
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
  description = "Region for the Next.js BFF. Singapore is close to the planned Render backend."
  type        = string
  default     = "sin1"
}

variable "neon_region_id" {
  description = "Neon database region. Singapore is close to the planned Render backend. Changing it replaces the project."
  type        = string
  default     = "aws-ap-southeast-1"
}

variable "neon_organization_id" {
  description = "Optional Neon organization ID; null uses the API key's default account context."
  type        = string
  default     = null
}
