# SPEC-2026-031 — result_collector Lambda + EventBridge rate(5 min) + colas SQS opcionales

variable "enable_result_collector" {
  type        = bool
  default     = false
  description = "Lambda result_collector + schedule cada 5 min + colas scoring/notify."
}

variable "enable_result_queues" {
  type        = bool
  default     = false
  description = "Crear ScoringQueue y NotificationQueue para result_collector."
}

locals {
  result_collector_lambda_dir = "${path.module}/../lambdas/result_collector"
  result_collector_zip        = "${path.module}/.build/result_collector.zip"
  result_collector_repo_root  = abspath("${path.module}/../..")
  result_collector_src_files = concat(
    [for f in sort(fileset("${local.result_collector_repo_root}/src/dao", "**")) :
    "${local.result_collector_repo_root}/src/dao/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.result_collector_repo_root}/src/services", "**")) :
    "${local.result_collector_repo_root}/src/services/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.result_collector_repo_root}/src/models", "**")) :
    "${local.result_collector_repo_root}/src/models/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.result_collector_repo_root}/src/web", "**")) :
    "${local.result_collector_repo_root}/src/web/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.result_collector_repo_root}/src/scoring", "**")) :
    "${local.result_collector_repo_root}/src/scoring/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.result_collector_repo_root}/src/clients", "**")) :
    "${local.result_collector_repo_root}/src/clients/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
  )
  result_collector_py_files = sort(fileset("${local.result_collector_lambda_dir}", "*.py"))
  result_collector_hash = sha256(join("", concat(
    [
      filesha256("${path.module}/bin/build-result-collector-lambda.sh"),
      filesha256("${local.result_collector_lambda_dir}/requirements.txt"),
    ],
    [for f in local.result_collector_py_files : filesha256("${local.result_collector_lambda_dir}/${f}")],
    [for p in local.result_collector_src_files : filesha256(p)],
  )))
}

resource "aws_sqs_queue" "scoring" {
  count = var.enable_result_queues ? 1 : 0

  name                       = "prode-scoring-${var.env}"
  message_retention_seconds  = 86400
  visibility_timeout_seconds = 300
}

resource "aws_sqs_queue" "match_notifications" {
  count = var.enable_result_queues ? 1 : 0

  name                       = "prode-match-notify-${var.env}"
  message_retention_seconds  = 86400
  visibility_timeout_seconds = 120
}

resource "null_resource" "result_collector_package" {
  count = var.enable_result_collector ? 1 : 0

  triggers = {
    hash = local.result_collector_hash
  }

  provisioner "local-exec" {
    command     = "${path.module}/bin/build-result-collector-lambda.sh ${local.result_collector_lambda_dir} ${local.result_collector_zip}"
    interpreter = ["bash", "-c"]
  }
}

resource "aws_iam_role" "result_collector" {
  count = var.enable_result_collector ? 1 : 0

  name               = "prode-result-collector-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "result_collector_logs" {
  count = var.enable_result_collector ? 1 : 0

  role       = aws_iam_role.result_collector[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "result_collector_inline" {
  count = var.enable_result_collector ? 1 : 0

  statement {
    sid = "DynamoDB"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query",
      "dynamodb:Scan",
    ]
    resources = [
      module.prode_table.dynamodb_table_arn,
      "${module.prode_table.dynamodb_table_arn}/index/*",
    ]
  }

  dynamic "statement" {
    for_each = var.enable_result_queues ? [1] : []
    content {
      sid       = "SQS"
      actions   = ["sqs:SendMessage"]
      resources = [
        aws_sqs_queue.scoring[0].arn,
        aws_sqs_queue.match_notifications[0].arn,
      ]
    }
  }

  dynamic "statement" {
    for_each = var.tavily_secret_arn != "" ? [1] : []
    content {
      sid       = "TavilySecret"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [var.tavily_secret_arn]
    }
  }

  dynamic "statement" {
    for_each = var.enable_result_collector ? [1] : []
    content {
      sid = "BedrockParse"
      actions = [
        "bedrock:InvokeModel",
      ]
      resources = ["*"]
    }
  }
  dynamic "statement" {
    for_each = var.telegram_secret_arn != "" ? [1] : []
    content {
      sid       = "TelegramSecret"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [var.telegram_secret_arn]
    }
  }
}

resource "aws_iam_role_policy" "result_collector" {
  count = var.enable_result_collector ? 1 : 0

  name   = "result-collector-inline"
  role   = aws_iam_role.result_collector[0].id
  policy = data.aws_iam_policy_document.result_collector_inline[0].json
}

resource "aws_lambda_function" "result_collector" {
  count = var.enable_result_collector ? 1 : 0

  function_name = "prode-result-collector-${var.env}"
  role          = aws_iam_role.result_collector[0].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  timeout       = 120
  memory_size   = 512

  filename         = local.result_collector_zip
  source_code_hash = local.result_collector_hash

  environment {
    variables = {
      DYNAMODB_TABLE          = module.prode_table.dynamodb_table_id
      SCORING_QUEUE_URL       = var.enable_result_queues ? aws_sqs_queue.scoring[0].url : ""
      NOTIFICATION_QUEUE_URL  = var.enable_result_queues ? aws_sqs_queue.match_notifications[0].url : ""
      TAVILY_SECRET_ARN       = var.tavily_secret_arn
      TELEGRAM_SECRET_ARN     = var.telegram_secret_arn
      RESULT_PARSE_USE_BEDROCK = "false"
      RESULT_ADMIN_GATE_ENABLED = "true"
    }
  }

  depends_on = [null_resource.result_collector_package]
}

resource "aws_cloudwatch_event_rule" "result_collector" {
  count = var.enable_result_collector ? 1 : 0

  name                = "prode-result-collector-${var.env}"
  description         = "SPEC-031 — recolectar resultados incompletos cada 5 min"
  schedule_expression = "rate(5 minutes)"
}

resource "aws_cloudwatch_event_target" "result_collector" {
  count = var.enable_result_collector ? 1 : 0

  rule      = aws_cloudwatch_event_rule.result_collector[0].name
  target_id = "result-collector"
  arn       = aws_lambda_function.result_collector[0].arn

  input = jsonencode({ "trigger" = "scheduled" })
}

resource "aws_lambda_permission" "result_collector_eventbridge" {
  count = var.enable_result_collector ? 1 : 0

  statement_id  = "AllowEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.result_collector[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.result_collector[0].arn
}
