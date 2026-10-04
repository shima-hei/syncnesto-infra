resource "neon_project" "portfolio" {
  name                      = var.project_name
  org_id                    = var.neon_organization_id
  region_id                 = var.neon_region_id
  pg_version                = 17
  history_retention_seconds = 21600
  autoscaling_limit_min_cu  = 0.25
  autoscaling_limit_max_cu  = 0.25
  # Freeでは停止時間の明示指定をAPIが拒否するため、既定の自動停止を使う。

  branch {
    name          = "production"
    database_name = "syncnesto"
    role_name     = "syncnesto_owner"
  }

  primary_compute {
    name                     = "production"
    autoscaling_limit_min_cu = 0.25
    autoscaling_limit_max_cu = 0.25
  }

  lifecycle {
    prevent_destroy = true
  }
}
