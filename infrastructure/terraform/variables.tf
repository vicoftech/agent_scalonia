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

variable "telegram_bot_username" {
  type        = string
  default     = "ProdeBot"
  description = "Username del bot sin @ — deep links t.me/<bot>?start=<invite_id>"
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

variable "bedrock_model_id" {
  type        = string
  default     = "us.amazon.nova-pro-v1:0"
  description = "Inference profile Bedrock (evitar Anthropic en cuentas reseller). Nova Lite: us.amazon.nova-lite-v1:0"
}

variable "project_name" {
  type        = string
  default     = "prode-mundial"
  description = "Prefijo SSM y nombres del guardrail Bedrock (SPEC-2026-015)."
}

variable "sns_alerts_arn" {
  type        = string
  default     = ""
  description = "ARN SNS para alarma de bloqueos de guardrail (vacío = sin notificación)."
}

variable "aurora_sync_secret_arn" {
  type        = string
  default     = ""
  description = "ARN secreto DB KB. Vacío si manage_aurora_secret=true."
}

variable "manage_aurora_secret" {
  type        = bool
  default     = false
  description = "Crear secret prode-mundial/{env}/aurora-sync (aurora_db_password en tfvars)."
}

variable "aurora_db_username" {
  type    = string
  default = "dev_master"
}

variable "aurora_db_password" {
  type      = string
  default   = ""
  sensitive = true
}

variable "lambda_vpc_subnet_ids" {
  type        = list(string)
  default     = []
  description = "Subnets privadas para Lambdas KB (acceso RDS Proxy)."
}

variable "lambda_vpc_security_group_ids" {
  type        = list(string)
  default     = []
  description = "Security groups para Lambdas KB."
}

variable "rds_proxy_endpoint" {
  type        = string
  default     = ""
  description = "Host RDS Proxy (si el secret no incluye host)."
}

variable "db_name" {
  type        = string
  default     = "prode"
  description = "Base de datos Aurora."
}

variable "enable_kb_vpc_endpoints" {
  type        = bool
  default     = true
  description = "Crear VPC endpoints S3/Secrets/Bedrock para Lambdas KB."
}

variable "kb_aurora_security_group_id" {
  type        = string
  default     = ""
  description = "SG de aurora-pg-dev (ingress 5432 desde CIDR de la VPC Lambda)."
}

variable "kb_manage_aurora_lambda_vpc_ingress" {
  type        = bool
  default     = false
  description = "Terraform crea ingress 5432 en kb_aurora_security_group_id. false si ya existe (asap-dev: 10.0.0.0/16)."
}

variable "kb_ingest_timeout" {
  type        = number
  default     = 300
  description = "Timeout kb_ingest (segundos). 300 = 5 minutos."
}

variable "kb_ingest_reserved_concurrency" {
  type        = number
  default     = 3
  description = "Máx. ejecuciones paralelas kb_ingest (throttling Bedrock)."
}

variable "tavily_secret_arn" {
  type        = string
  default     = ""
  description = "Secrets Manager con API key Tavily para web_search_tool (opcional)."
}

variable "enable_github_oidc" {
  type        = bool
  default     = true
  description = "Crear proveedor OIDC de GitHub y rol IAM para CI (provider IAM solo en workspace dev)."
}

variable "github_repository" {
  type        = string
  default     = "vicoftech/agent_scalonia"
  description = "Repositorio GitHub org/repo para el claim sub de OIDC."
}

variable "github_actions_environment" {
  type        = string
  default     = ""
  description = "Nombre del GitHub Environment (development | staging | production). Vacío = inferido desde var.env."
}

