variable "database_host" {
  type = string
}
variable "pooled_host" {
  type = string
}
variable "database_name" {
  type = string
}
variable "database_owner" {
  type = string
}
variable "database_owner_password" {
  type      = string
  sensitive = true
  ephemeral = true
}
