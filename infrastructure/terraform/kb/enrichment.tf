# SPEC-2026-023 — cola + Lambda dispatcher de enriquecimiento KB

locals {
  kb_enrichment_zip = "${var.terraform_root}/.build/kb_enrichment_dispatcher.zip"
}

resource "null_resource" "kb_enrichment_package" {
  count = local.kb_lambda_enabled ? 1 : 0

  triggers = {
    hash = sha256(join("", [
      filesha256("${local.repo_root}/infrastructure/lambdas/kb_enrichment_dispatcher/handler.py"),
      filesha256("${local.repo_root}/src/kb/kb_enrichment_service.py"),
      filesha256("${local.repo_root}/src/kb/enrichment_queue.py"),
      filesha256("${local.repo_root}/src/kb/cache.py"),
    ]))
  }

  provisioner "local-exec" {
    command     = "${var.terraform_root}/bin/build-kb-lambda.sh ${local.repo_root} kb_enrichment_dispatcher ${local.kb_enrichment_zip}"
    interpreter = ["bash", "-c"]
  }
}

resource "aws_sqs_queue" "kb_enrichment" {
  count = local.kb_lambda_enabled ? 1 : 0

  name                       = "${var.project_name}-kb-enrichment-${var.env}"
  visibility_timeout_seconds = 120
  message_retention_seconds  = 86400
}

resource "aws_iam_role" "kb_enrichment_dispatcher" {
  count = local.kb_lambda_enabled ? 1 : 0

  name               = "${var.project_name}-kb-enrichment-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.kb_lambda_assume.json
}

data "aws_iam_policy_document" "kb_enrichment_dispatcher" {
  count = local.kb_lambda_enabled ? 1 : 0

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
    sid = "SQSConsume"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
    ]
    resources = [aws_sqs_queue.kb_enrichment[0].arn]
  }

  statement {
    sid = "DynamoDB"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
    ]
    resources = [var.dynamodb_table_arn]
  }

  statement {
    sid     = "S3PutEnriched"
    actions = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.kb_documents.arn}/enriched/*"]
  }
}

resource "aws_iam_role_policy" "kb_enrichment_dispatcher" {
  count = local.kb_lambda_enabled ? 1 : 0

  name   = "inline"
  role   = aws_iam_role.kb_enrichment_dispatcher[0].id
  policy = data.aws_iam_policy_document.kb_enrichment_dispatcher[0].json
}

resource "aws_lambda_function" "kb_enrichment_dispatcher" {
  count = local.kb_lambda_enabled ? 1 : 0

  function_name = "${var.project_name}-kb-enrichment-${var.env}"
  role          = aws_iam_role.kb_enrichment_dispatcher[0].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 256

  filename         = local.kb_enrichment_zip
  source_code_hash = null_resource.kb_enrichment_package[0].triggers.hash

  environment {
    variables = {
      DYNAMODB_TABLE = var.dynamodb_table_name
      KB_S3_BUCKET   = aws_s3_bucket.kb_documents.id
      LOG_LEVEL      = "INFO"
    }
  }

  depends_on = [null_resource.kb_enrichment_package]
}

resource "aws_lambda_event_source_mapping" "kb_enrichment_sqs" {
  count = local.kb_lambda_enabled ? 1 : 0

  event_source_arn = aws_sqs_queue.kb_enrichment[0].arn
  function_name    = aws_lambda_function.kb_enrichment_dispatcher[0].arn
  batch_size       = 1
}

resource "aws_ssm_parameter" "kb_enrichment_queue" {
  count = local.kb_lambda_enabled ? 1 : 0

  name  = "/${var.project_name}/${var.env}/kb_enrichment_queue_url"
  type  = "String"
  value = aws_sqs_queue.kb_enrichment[0].url
}
