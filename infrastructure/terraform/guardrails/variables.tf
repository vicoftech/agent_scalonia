variable "project_name" {
  type        = string
  description = "Prefijo del proyecto (SSM y nombres de recursos)."
  default     = "prode-mundial"
}

variable "env" {
  type        = string
  description = "Entorno (dev, staging, prod)."
}

variable "sns_alerts_arn" {
  type        = string
  description = "ARN SNS para alertas DevOps (vacío = alarma sin acciones)."
  default     = ""
}
