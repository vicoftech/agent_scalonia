# Cluster Aurora PostgreSQL existente (no se provisiona — TASK-000-006 consume recurso ya creado).
variable "aurora_cluster_identifier" {
  type        = string
  default     = ""
  description = "Si se informa, expone endpoints vía data source (ej. aurora-pg-asap-dev)."
}

data "aws_rds_cluster" "prode" {
  count              = var.aurora_cluster_identifier != "" ? 1 : 0
  cluster_identifier = var.aurora_cluster_identifier
}
