# 認証情報はそれぞれVERCEL_API_TOKEN / NEON_API_KEYから読む。
provider "vercel" {
  team = var.vercel_team_id
}

provider "neon" {}
