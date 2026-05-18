data "aws_caller_identity" "kb" {}
data "aws_region" "kb" {}

locals {
  repo_root        = abspath("${var.terraform_root}/../..")
  kb_ingest_zip    = "${var.terraform_root}/.build/kb_ingest.zip"
  kb_query_zip     = "${var.terraform_root}/.build/kb_query.zip"
  aurora_secret_arn = var.aurora_sync_secret_arn != "" ? var.aurora_sync_secret_arn : (
    var.manage_aurora_secret ? aws_secretsmanager_secret.aurora_sync[0].arn : ""
  )
  kb_lambda_enabled = (
    local.aurora_secret_arn != ""
    && var.rds_proxy_endpoint != ""
    && length(var.lambda_vpc_subnet_ids) > 0
  )
  kb_lambda_env = {
    AURORA_SYNC_SECRET_ARN = local.aurora_secret_arn
    RDS_PROXY_ENDPOINT     = var.rds_proxy_endpoint
    DB_NAME                = var.db_name
    LOG_LEVEL              = "INFO"
    BEDROCK_EMBED_MODEL_ID = var.bedrock_embed_model_id
  }
}

resource "null_resource" "kb_ingest_package" {
  count = local.kb_lambda_enabled ? 1 : 0
  triggers = {
    hash = sha256(join("", [
      filesha256("${local.repo_root}/infrastructure/lambdas/kb_ingest/handler.py"),
      filesha256("${local.repo_root}/infrastructure/lambdas/kb_ingest/requirements.txt"),
      filesha256("${local.repo_root}/src/kb/chunking.py"),
      filesha256("${local.repo_root}/src/kb/pg.py"),
      filesha256("${local.repo_root}/src/kb/embeddings.py"),
      filesha256("${local.repo_root}/src/kb/pdf_extract.py"),
    ]))
  }
  provisioner "local-exec" {
    command     = "${var.terraform_root}/bin/build-kb-lambda.sh ${local.repo_root} kb_ingest ${local.kb_ingest_zip}"
    interpreter = ["bash", "-c"]
  }
}

resource "null_resource" "kb_query_package" {
  count = local.kb_lambda_enabled ? 1 : 0
  triggers = {
    hash = sha256(join("", [
      filesha256("${local.repo_root}/infrastructure/lambdas/kb_query/handler.py"),
      filesha256("${local.repo_root}/infrastructure/lambdas/kb_query/requirements.txt"),
      filesha256("${local.repo_root}/src/kb/pg.py"),
      filesha256("${local.repo_root}/src/kb/embeddings.py"),
    ]))
  }
  provisioner "local-exec" {
    command     = "${var.terraform_root}/bin/build-kb-lambda.sh ${local.repo_root} kb_query ${local.kb_query_zip}"
    interpreter = ["bash", "-c"]
  }
}

data "aws_iam_policy_document" "kb_lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "kb_lambda" {
  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${data.aws_region.kb.region}:${data.aws_caller_identity.kb.account_id}:*"]
  }

  statement {
    sid = "VpcNetwork"
    actions = [
      "ec2:CreateNetworkInterface",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "Secrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.aurora_secret_arn]
  }

  statement {
    sid       = "BedrockEmbed"
    actions   = ["bedrock:InvokeModel"]
    resources = ["arn:aws:bedrock:${data.aws_region.kb.region}::foundation-model/amazon.titan-embed*"]
  }
}

data "aws_iam_policy_document" "kb_ingest_extra" {
  statement {
    sid = "S3Read"
    actions = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.kb_documents.arn}/*"]
  }

}

resource "aws_iam_role" "kb_ingest" {
  count              = local.kb_lambda_enabled ? 1 : 0
  name               = "${var.project_name}-kb-ingest-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.kb_lambda_assume.json
}

resource "aws_iam_role_policy" "kb_ingest" {
  count  = local.kb_lambda_enabled ? 1 : 0
  name   = "inline"
  role   = aws_iam_role.kb_ingest[0].id
  policy = data.aws_iam_policy_document.kb_lambda.json
}

resource "aws_iam_role_policy" "kb_ingest_s3" {
  count  = local.kb_lambda_enabled ? 1 : 0
  name   = "s3"
  role   = aws_iam_role.kb_ingest[0].id
  policy = data.aws_iam_policy_document.kb_ingest_extra.json
}

resource "aws_iam_role" "kb_query" {
  count              = local.kb_lambda_enabled ? 1 : 0
  name               = "${var.project_name}-kb-query-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.kb_lambda_assume.json
}

resource "aws_iam_role_policy" "kb_query" {
  count  = local.kb_lambda_enabled ? 1 : 0
  name   = "inline"
  role   = aws_iam_role.kb_query[0].id
  policy = data.aws_iam_policy_document.kb_lambda.json
}

resource "aws_lambda_function" "kb_ingest" {
  count = local.kb_lambda_enabled ? 1 : 0

  function_name = "${var.project_name}-kb-ingest-${var.env}"
  role          = aws_iam_role.kb_ingest[0].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  timeout       = var.kb_ingest_timeout
  memory_size   = 1024

  reserved_concurrent_executions = var.kb_ingest_reserved_concurrency

  filename         = local.kb_ingest_zip
  source_code_hash = null_resource.kb_ingest_package[0].triggers.hash

  vpc_config {
    subnet_ids         = var.lambda_vpc_subnet_ids
    security_group_ids = var.lambda_vpc_security_group_ids
  }

  environment {
    variables = local.kb_lambda_env
  }

  depends_on = [null_resource.kb_ingest_package]
}

resource "aws_lambda_function" "kb_query" {
  count = local.kb_lambda_enabled ? 1 : 0

  function_name = "${var.project_name}-kb-query-${var.env}"
  role          = aws_iam_role.kb_query[0].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  timeout       = 30
  memory_size   = 256

  filename         = local.kb_query_zip
  source_code_hash = null_resource.kb_query_package[0].triggers.hash

  vpc_config {
    subnet_ids         = var.lambda_vpc_subnet_ids
    security_group_ids = var.lambda_vpc_security_group_ids
  }

  environment {
    variables = local.kb_lambda_env
  }

  depends_on = [null_resource.kb_query_package]
}

resource "aws_lambda_permission" "kb_ingest_s3" {
  count = local.kb_lambda_enabled ? 1 : 0

  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.kb_ingest[0].function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.kb_documents.arn
}

resource "aws_s3_bucket_notification" "kb_ingest" {
  count = local.kb_lambda_enabled ? 1 : 0

  bucket = aws_s3_bucket.kb_documents.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.kb_ingest[0].arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".md"
  }

  lambda_function {
    lambda_function_arn = aws_lambda_function.kb_ingest[0].arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = ".pdf"
  }

  depends_on = [aws_lambda_permission.kb_ingest_s3]
}

resource "aws_ssm_parameter" "kb_query_lambda" {
  count = local.kb_lambda_enabled ? 1 : 0

  name  = "/${var.project_name}/${var.env}/kb_query_lambda"
  type  = "String"
  value = aws_lambda_function.kb_query[0].function_name
}
