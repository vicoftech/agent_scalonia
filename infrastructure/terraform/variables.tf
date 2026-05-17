variable "env" {
  type        = string
  description = "Deployment environment (e.g. dev, staging, prod)."
}

variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region for all resources in this stack."
}

variable "aws_profile" {
  type        = string
  default     = ""
  description = "Perfil ~/.aws/credentials para uso local (ej. asap_dev). Vacío = cadena por defecto (CI con keys)."
}

variable "aurora_cluster_identifier" {
  type        = string
  default     = ""
  description = "Cluster Aurora existente (data source). Vacío = sin outputs Aurora."
}

variable "telegram_secret_arn" {
  type        = string
  description = "ARN del secreto SCALONIA_TELEGRAM_BOT_TOKEN en Secrets Manager."
}

variable "terraform_state_bucket" {
  type        = string
  description = "Bucket S3 del backend remoto (bootstrap: prode-terraform-state-<account_id>)."
}

variable "terraform_state_lock_table" {
  type        = string
  description = "Tabla DynamoDB para lock del state (bootstrap: prode-terraform-state-lock)."
}

variable "terraform_state_key" {
  type        = string
  default     = "prode/terraform.tfstate"
  description = "Key del objeto .tfstate en S3 (workspace agrega prefijo env:/<ws>/)."
}
