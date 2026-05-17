# Bedrock AgentCore Runtime — deploy del agente Strands (sin agentcore deploy CLI)

data "aws_caller_identity" "current" {}

locals {
  repo_root = abspath("${path.module}/../..")
  agent_zip = "${path.module}/.build/agent-runtime.zip"

  agent_source_files = concat(
    [for f in sort(fileset("${local.repo_root}/agent", "**")) :
    "${local.repo_root}/agent/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.repo_root}/src/kb", "**")) :
    "${local.repo_root}/src/kb/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
  )
  agent_source_hash = sha256(join("", concat(
    [filesha256("${local.repo_root}/requirements-agent.txt")],
    [filesha256("${path.module}/bin/build-agent-zip.sh")],
    [for p in local.agent_source_files : filesha256(p)],
  )))
}

resource "aws_s3_bucket" "agent_code" {
  bucket = "prode-agent-code-${data.aws_caller_identity.current.account_id}"

  lifecycle {
    prevent_destroy = false
  }
}

resource "aws_s3_bucket_versioning" "agent_code" {
  bucket = aws_s3_bucket.agent_code.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_public_access_block" "agent_code" {
  bucket = aws_s3_bucket.agent_code.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "null_resource" "agent_package" {
  triggers = {
    source_hash = local.agent_source_hash
  }

  provisioner "local-exec" {
    command     = "${path.module}/bin/build-agent-zip.sh ${local.repo_root} ${local.agent_zip}"
    interpreter = ["bash", "-c"]
  }
}

resource "aws_s3_object" "agent_runtime_code" {
  bucket = aws_s3_bucket.agent_code.id
  key    = "runtimes/${var.env}/agent-runtime-${local.agent_source_hash}.zip"
  source = local.agent_zip
  etag   = local.agent_source_hash

  depends_on = [null_resource.agent_package]
}

data "aws_iam_policy_document" "agent_runtime_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "agent_runtime" {
  statement {
    sid = "BedrockModels"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
      "bedrock:Converse",
      "bedrock:ConverseStream",
    ]
    resources = [
      "*",
      "arn:aws:bedrock:${var.aws_region}::foundation-model/*",
      "arn:aws:bedrock:${var.aws_region}:${data.aws_caller_identity.current.account_id}:inference-profile/*",
    ]
  }

  statement {
    sid = "BedrockGuardrail"
    actions = [
      "bedrock:GetGuardrail",
      "bedrock:ApplyGuardrail",
    ]
    resources = [module.guardrails.guardrail_arn]
  }

  statement {
    sid = "DynamoDBCache"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query",
    ]
    resources = [
      module.prode_table.dynamodb_table_arn,
      "${module.prode_table.dynamodb_table_arn}/index/*",
    ]
  }

  statement {
    sid       = "Secrets"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = compact([var.telegram_secret_arn, var.tavily_secret_arn])
  }

  dynamic "statement" {
    for_each = module.kb.kb_query_lambda_arn != "" ? [1] : []
    content {
      sid       = "KbQueryLambda"
      actions   = ["lambda:InvokeFunction"]
      resources = [module.kb.kb_query_lambda_arn]
    }
  }

  statement {
    sid = "Logs"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]
    resources = ["arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/bedrock-agentcore/*"]
  }

  statement {
    sid       = "AgentCodeS3"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.agent_code.arn}/*"]
  }
}

resource "aws_iam_role" "agent_runtime" {
  name               = "prode-agent-runtime-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.agent_runtime_assume.json
}

resource "aws_iam_role_policy" "agent_runtime" {
  name   = "inline"
  role   = aws_iam_role.agent_runtime.id
  policy = data.aws_iam_policy_document.agent_runtime.json
}

resource "aws_bedrockagentcore_agent_runtime" "prode" {
  agent_runtime_name = "prode_mundial_${var.env}"
  description        = "Prode Mundial 2026 — ${var.env} — code ${local.agent_source_hash}"
  role_arn           = aws_iam_role.agent_runtime.arn

  environment_variables = merge(
    {
      DYNAMODB_TABLE    = module.prode_table.dynamodb_table_id
      LOG_LEVEL         = "INFO"
      BEDROCK_MODEL_ID  = var.bedrock_model_id
      GUARDRAIL_ID      = module.guardrails.guardrail_id
      GUARDRAIL_VERSION = module.guardrails.guardrail_version
      AWS_REGION        = var.aws_region
    },
    var.tavily_secret_arn != "" ? { TAVILY_SECRET_ARN = var.tavily_secret_arn } : {},
    module.kb.kb_query_lambda_name != "" ? {
      KB_QUERY_LAMBDA_NAME = module.kb.kb_query_lambda_name
    } : {},
  )

  agent_runtime_artifact {
    code_configuration {
      entry_point = ["agent/main.py"]
      runtime     = "PYTHON_3_12"
      code {
        s3 {
          bucket     = aws_s3_bucket.agent_code.id
          prefix     = aws_s3_object.agent_runtime_code.key
          version_id = aws_s3_object.agent_runtime_code.version_id
        }
      }
    }
  }

  network_configuration {
    network_mode = "PUBLIC"
  }

  depends_on = [
    aws_s3_object.agent_runtime_code,
    module.prode_table,
    module.guardrails,
    module.kb,
  ]
}

resource "aws_bedrockagentcore_agent_runtime_endpoint" "live" {
  name                  = "LIVE"
  description           = "Endpoint estable para webhooks (${var.env})"
  agent_runtime_id      = aws_bedrockagentcore_agent_runtime.prode.agent_runtime_id
  agent_runtime_version = aws_bedrockagentcore_agent_runtime.prode.agent_runtime_version

  depends_on = [aws_bedrockagentcore_agent_runtime.prode]
}
