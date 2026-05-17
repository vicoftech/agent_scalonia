variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "aws_profile" {
  type        = string
  default     = "asap_dev"
  description = "Perfil local (~/.aws/credentials)."
}

variable "state_bucket_name" {
  type        = string
  default     = ""
  description = "Vacío = prode-terraform-state-<account_id> (único globalmente)."
}

variable "lock_table_name" {
  type    = string
  default = "prode-terraform-state-lock"
}
