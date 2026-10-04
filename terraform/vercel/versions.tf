terraform {
  required_version = ">= 1.14.0, < 2.0.0"

  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "~> 3.7"
    }
    vercel = {
      source  = "vercel/vercel"
      version = "~> 5.19.0"
    }
    neon = {
      source  = "kislerdm/neon"
      version = "~> 0.18.0"
    }
  }
}
