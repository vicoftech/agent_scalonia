# Lambdas en VPC privada necesitan endpoints para S3, Secrets Manager y Bedrock.

data "aws_subnet" "lambda_first" {
  count = var.enable_vpc_endpoints && length(var.lambda_vpc_subnet_ids) > 0 ? 1 : 0
  id    = var.lambda_vpc_subnet_ids[0]
}

data "aws_route_tables" "lambda_vpc" {
  count  = var.enable_vpc_endpoints && length(var.lambda_vpc_subnet_ids) > 0 ? 1 : 0
  vpc_id = data.aws_subnet.lambda_first[0].vpc_id
}

data "aws_vpc" "lambda_vpc" {
  count = var.enable_vpc_endpoints && length(var.lambda_vpc_subnet_ids) > 0 ? 1 : 0
  id    = data.aws_subnet.lambda_first[0].vpc_id
}

data "aws_security_group" "aurora" {
  count = var.enable_vpc_endpoints && var.aurora_security_group_id != "" ? 1 : 0
  id    = var.aurora_security_group_id
}

locals {
  lambda_vpc_cidr = var.enable_vpc_endpoints && length(data.aws_vpc.lambda_vpc) > 0 ? data.aws_vpc.lambda_vpc[0].cidr_block : null

  kb_aurora_rule_description = "Prode KB Lambdas (${var.project_name} ${var.env})"

  # Omitir solo si ya hay 5432 desde el mismo CIDR creado fuera de este módulo (p. ej. 10.0.0.0/16 legacy).
  aurora_has_foreign_lambda_vpc_ingress = length([
    for rule in try(data.aws_security_group.aurora[0].ingress, []) : rule
    if rule.from_port == 5432 && rule.to_port == 5432
      && contains(try(rule.cidr_blocks, []), local.lambda_vpc_cidr)
      && try(rule.description, "") != local.kb_aurora_rule_description
  ]) > 0
}

resource "aws_security_group" "vpc_endpoints" {
  count = var.enable_vpc_endpoints ? 1 : 0

  name        = "${var.project_name}-kb-vpce-${var.env}"
  description = "Interface endpoints para Lambdas KB"
  vpc_id      = data.aws_subnet.lambda_first[0].vpc_id

  ingress {
    description     = "HTTPS desde Lambdas KB"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    security_groups = var.lambda_vpc_security_group_ids
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_vpc_endpoint" "s3" {
  count = var.enable_vpc_endpoints ? 1 : 0

  vpc_id            = data.aws_subnet.lambda_first[0].vpc_id
  service_name      = "com.amazonaws.${data.aws_region.kb.name}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = data.aws_route_tables.lambda_vpc[0].ids
}

resource "aws_vpc_endpoint" "secretsmanager" {
  count = var.enable_vpc_endpoints ? 1 : 0

  vpc_id              = data.aws_subnet.lambda_first[0].vpc_id
  service_name        = "com.amazonaws.${data.aws_region.kb.name}.secretsmanager"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.lambda_vpc_subnet_ids
  security_group_ids  = [aws_security_group.vpc_endpoints[0].id]
  private_dns_enabled = true
}

# Aurora SG puede tener ya 5432 desde el CIDR de la VPC Lambda (p. ej. 10.0.0.0/16).
resource "aws_security_group_rule" "aurora_from_lambda_vpc" {
  count = var.enable_vpc_endpoints && var.aurora_security_group_id != "" && !local.aurora_has_foreign_lambda_vpc_ingress ? 1 : 0

  type              = "ingress"
  from_port         = 5432
  to_port           = 5432
  protocol          = "tcp"
  security_group_id = var.aurora_security_group_id
  cidr_blocks       = [local.lambda_vpc_cidr]
  description       = local.kb_aurora_rule_description
}

resource "aws_vpc_endpoint" "bedrock_runtime" {
  count = var.enable_vpc_endpoints ? 1 : 0

  vpc_id              = data.aws_subnet.lambda_first[0].vpc_id
  service_name        = "com.amazonaws.${data.aws_region.kb.name}.bedrock-runtime"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = var.lambda_vpc_subnet_ids
  security_group_ids  = [aws_security_group.vpc_endpoints[0].id]
  private_dns_enabled = true
}

