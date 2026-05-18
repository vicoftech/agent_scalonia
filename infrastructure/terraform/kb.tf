# SPEC-2026-017 — S3 + Lambdas VPC (ingest + query pgvector)

module "kb" {
  source = "./kb"

  project_name   = var.project_name
  env            = var.env
  terraform_root = abspath(path.module)

  aurora_sync_secret_arn        = var.aurora_sync_secret_arn
  manage_aurora_secret          = var.manage_aurora_secret
  aurora_db_username            = var.aurora_db_username
  aurora_db_password            = var.aurora_db_password
  rds_proxy_endpoint            = var.rds_proxy_endpoint
  db_name                       = var.db_name
  lambda_vpc_subnet_ids         = var.lambda_vpc_subnet_ids
  lambda_vpc_security_group_ids = var.lambda_vpc_security_group_ids
  enable_vpc_endpoints          = var.enable_kb_vpc_endpoints
  aurora_security_group_id            = var.kb_aurora_security_group_id
  manage_aurora_lambda_vpc_ingress    = var.kb_manage_aurora_lambda_vpc_ingress
  kb_ingest_timeout                = var.kb_ingest_timeout
  kb_ingest_reserved_concurrency   = var.kb_ingest_reserved_concurrency
}
