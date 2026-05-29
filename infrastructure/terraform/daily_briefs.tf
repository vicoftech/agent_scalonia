# SPEC-2026-045 — briefs diarios (09:00 Buenos Aires)

variable "enable_daily_briefs" {
  type        = bool
  default     = false
  description = "Tabla ProdeBriefTable + Lambda orchestrator + cron diario 09:00 ART."
}

locals {
  daily_brief_lambda_dir = "${path.module}/../lambdas/daily_brief_orchestrator"
  daily_brief_zip        = "${path.module}/.build/daily_brief_orchestrator.zip"
  daily_brief_repo_root  = abspath("${path.module}/../..")
  daily_brief_src_files = concat(
    [for f in sort(fileset("${local.daily_brief_repo_root}/src/dao", "**")) :
    "${local.daily_brief_repo_root}/src/dao/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.daily_brief_repo_root}/src/services", "**")) :
    "${local.daily_brief_repo_root}/src/services/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.daily_brief_repo_root}/src/fixtures", "**")) :
    "${local.daily_brief_repo_root}/src/fixtures/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.daily_brief_repo_root}/src/utils", "**")) :
    "${local.daily_brief_repo_root}/src/utils/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
  )
  daily_brief_py_files = sort(fileset("${local.daily_brief_lambda_dir}", "*.py"))
  daily_brief_hash = sha256(join("", concat(
    [
      filesha256("${path.module}/bin/build-daily-brief-orchestrator-lambda.sh"),
      filesha256("${local.daily_brief_lambda_dir}/requirements.txt"),
    ],
    [for f in local.daily_brief_py_files : filesha256("${local.daily_brief_lambda_dir}/${f}")],
    [for p in local.daily_brief_src_files : filesha256(p)],
  )))
  brief_table_name = "ProdeBriefTable-${var.env}"
}

resource "aws_dynamodb_table" "prode_brief" {
  count = var.enable_daily_briefs ? 1 : 0

  name         = local.brief_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "partition_key"
  range_key    = "sort_key"

  attribute {
    name = "partition_key"
    type = "S"
  }

  attribute {
    name = "sort_key"
    type = "S"
  }

  ttl {
    attribute_name = "ttl_expiry"
    enabled        = true
  }

  tags = {
    Project = "prode-mundial"
    Env     = var.env
    Spec    = "SPEC-2026-045"
  }
}

resource "null_resource" "daily_brief_package" {
  count = var.enable_daily_briefs ? 1 : 0

  triggers = {
    hash = local.daily_brief_hash
  }

  provisioner "local-exec" {
    command     = "${path.module}/bin/build-daily-brief-orchestrator-lambda.sh ${local.daily_brief_lambda_dir} ${local.daily_brief_zip}"
    interpreter = ["bash", "-c"]
  }
}

resource "aws_iam_role" "daily_brief_orchestrator" {
  count = var.enable_daily_briefs ? 1 : 0

  name               = "prode-daily-brief-orchestrator-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "daily_brief_orchestrator_logs" {
  count = var.enable_daily_briefs ? 1 : 0

  role       = aws_iam_role.daily_brief_orchestrator[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "daily_brief_orchestrator_inline" {
  count = var.enable_daily_briefs ? 1 : 0

  statement {
    sid = "BriefTable"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      aws_dynamodb_table.prode_brief[0].arn,
      "${aws_dynamodb_table.prode_brief[0].arn}/index/*",
    ]
  }

  statement {
    sid = "FixtureRead"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      module.prode_table.dynamodb_table_arn,
      "${module.prode_table.dynamodb_table_arn}/index/*",
    ]
  }

  statement {
    sid = "AgentCoreInvoke"
    actions = [
      "bedrock-agentcore:InvokeAgentRuntime",
    ]
    resources = [
      aws_bedrockagentcore_agent_runtime.prode.agent_runtime_arn,
      aws_bedrockagentcore_agent_runtime_endpoint.live.agent_runtime_endpoint_arn,
    ]
  }
}

resource "aws_iam_role_policy" "daily_brief_orchestrator" {
  count = var.enable_daily_briefs ? 1 : 0

  name   = "inline"
  role   = aws_iam_role.daily_brief_orchestrator[0].id
  policy = data.aws_iam_policy_document.daily_brief_orchestrator_inline[0].json
}

resource "aws_lambda_function" "daily_brief_orchestrator" {
  count = var.enable_daily_briefs ? 1 : 0

  function_name = "prode-daily-brief-orchestrator-${var.env}"
  role          = aws_iam_role.daily_brief_orchestrator[0].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  timeout       = 900
  memory_size   = 1024

  filename         = local.daily_brief_zip
  source_code_hash = local.daily_brief_hash

  environment {
    variables = merge(
      {
        ENV                         = var.env
        BRIEF_TABLE                 = aws_dynamodb_table.prode_brief[0].name
        DYNAMODB_TABLE              = module.prode_table.dynamodb_table_id
        ENABLE_DAILY_BRIEFS         = "true"
        AGENTCORE_RUNTIME_ARN       = aws_bedrockagentcore_agent_runtime.prode.agent_runtime_arn
        AGENTCORE_RUNTIME_QUALIFIER = aws_bedrockagentcore_agent_runtime_endpoint.live.name
        BRIEF_CONCURRENCY           = "5"
        BRIEF_REGENERATE_FINISHED   = "true"
      },
      module.kb.kb_query_lambda_name != "" ? {
        KB_QUERY_LAMBDA_NAME = module.kb.kb_query_lambda_name
      } : {},
      var.tavily_secret_arn != "" ? {
        TAVILY_SECRET_ARN = var.tavily_secret_arn
      } : {},
    )
  }

  depends_on = [null_resource.daily_brief_package]
}

data "aws_iam_policy_document" "scheduler_daily_brief_assume" {
  count = var.enable_daily_briefs ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler_daily_brief" {
  count = var.enable_daily_briefs ? 1 : 0

  name               = "prode-scheduler-daily-brief-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.scheduler_daily_brief_assume[0].json
}

resource "aws_iam_role_policy" "scheduler_daily_brief_invoke" {
  count = var.enable_daily_briefs ? 1 : 0

  name = "invoke-daily-brief"
  role = aws_iam_role.scheduler_daily_brief[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.daily_brief_orchestrator[0].arn
    }]
  })
}

resource "aws_scheduler_schedule" "daily_brief" {
  count = var.enable_daily_briefs ? 1 : 0

  name       = "prode-daily-brief-${var.env}"
  group_name = "default"

  schedule_expression          = "cron(0 9 * * ? *)"
  schedule_expression_timezone = "America/Argentina/Buenos_Aires"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.daily_brief_orchestrator[0].arn
    role_arn = aws_iam_role.scheduler_daily_brief[0].arn
    input    = jsonencode({ job = "daily_brief" })
  }
}

resource "aws_lambda_permission" "scheduler_daily_brief" {
  count = var.enable_daily_briefs ? 1 : 0

  statement_id  = "AllowSchedulerDailyBrief"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.daily_brief_orchestrator[0].function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.daily_brief[0].arn
}

output "brief_table_name" {
  description = "DynamoDB ProdeBriefTable"
  value       = var.enable_daily_briefs ? aws_dynamodb_table.prode_brief[0].name : null
}

output "daily_brief_orchestrator_lambda" {
  value = var.enable_daily_briefs ? aws_lambda_function.daily_brief_orchestrator[0].function_name : null
}
