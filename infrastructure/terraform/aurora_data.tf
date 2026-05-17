# Cluster Aurora PostgreSQL existente (no se provisiona — TASK-000-006 consume recurso ya creado).

data "aws_rds_cluster" "prode" {
  count              = var.aurora_cluster_identifier != "" ? 1 : 0
  cluster_identifier = var.aurora_cluster_identifier
}
