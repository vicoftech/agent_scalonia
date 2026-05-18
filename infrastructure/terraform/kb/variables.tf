variable "project_name" {
  type    = string
  default = "prode-mundial"
}

variable "env" {
  type = string
}

variable "terraform_root" {
  type        = string
  description = "Ruta absoluta a infrastructure/terraform."
}

variable "aurora_sync_secret_arn" {
  type        = string
  default     = ""
  description = "ARN secreto DB. Si vacío y manage_aurora_secret=true, usa el creado por este módulo."
}

variable "manage_aurora_secret" {
  type        = bool
  default     = false
  description = "Crear secret prode-mundial/<env>/aurora-sync desde aurora_db_username y aurora_db_password."
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

variable "rds_proxy_endpoint" {
  type        = string
  default     = ""
  description = "Hostname RDS Proxy."
}

variable "db_name" {
  type    = string
  default = "prode"
}

variable "lambda_vpc_subnet_ids" {
  type        = list(string)
  default     = []
  description = "Subnets privadas con ruta al RDS Proxy."
}

variable "lambda_vpc_security_group_ids" {
  type        = list(string)
  default     = []
  description = "SG que permite egress al proxy (5432)."
}

variable "bedrock_embed_model_id" {
  type    = string
  default = "amazon.titan-embed-text-v2:0"
}

variable "enable_vpc_endpoints" {
  type        = bool
  default     = true
  description = "S3 Gateway + Secrets Manager + Bedrock Runtime interface endpoints para Lambdas en VPC."
}

variable "aurora_security_group_id" {
  type        = string
  default     = ""
  description = "SG del cluster Aurora (ingress 5432 desde VPC de las Lambdas)."
}

variable "manage_aurora_lambda_vpc_ingress" {
  type        = bool
  default     = false
  description = "Crear regla ingress 5432 en aurora_security_group_id desde el CIDR de la VPC Lambda. false si la regla ya existe (evita InvalidPermission.Duplicate)."
}

variable "kb_ingest_timeout" {
  type        = number
  default     = 300
  description = "Timeout kb_ingest en segundos (máx. 900). 300 = 5 min."
}

variable "kb_ingest_reserved_concurrency" {
  type        = number
  default     = 3
  description = "Máximo de ejecuciones paralelas de kb_ingest (evita throttling Bedrock embed)."
}
