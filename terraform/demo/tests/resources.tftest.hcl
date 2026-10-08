mock_provider "neon" {}
mock_provider "random" {}

run "reject_unconfirmed_free_plan" {
  command         = plan
  expect_failures = [neon_project.demo]
}

run "empty_dedicated_project" {
  command = plan
  variables {
    free_plan_confirmed = true
  }
  assert {
    condition     = neon_project.demo.name == "syncnesto-demo" && neon_project.demo.pg_version == 17 && neon_project.demo.autoscaling_limit_max_cu == 0.25 && neon_project.demo.history_retention_seconds == 21600
    error_message = "Demo must use a new project with the bounded Free configuration."
  }
  assert {
    condition     = random_password.jwt.length == 64 && random_password.bff.length == 64 && random_password.cron.length == 64
    error_message = "Demo must generate independent authentication and cleanup credentials."
  }
}
