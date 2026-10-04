variable "aws_region" {
  description = "AWS region used by LocalStack."
  type        = string
  default     = "ap-northeast-1"
}

variable "project_name" {
  description = "Prefix for local learning resources."
  type        = string
  default     = "syncnesto"
}
