# Lambda Telegram + HTTP API POST /webhook/telegram — TASK-000-004

locals {
  telegram_lambda_dir  = "${path.module}/../lambdas/telegram_webhook"
  telegram_lambda_zip  = "${path.module}/.build/telegram_webhook.zip"
  telegram_repo_root   = abspath("${path.module}/../..")
  telegram_src_files = concat(
    [for f in sort(fileset("${local.telegram_repo_root}/src/dao", "**")) :
    "${local.telegram_repo_root}/src/dao/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.telegram_repo_root}/src/services", "**")) :
    "${local.telegram_repo_root}/src/services/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.telegram_repo_root}/src/utils", "**")) :
    "${local.telegram_repo_root}/src/utils/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.telegram_repo_root}/src/kb", "**")) :
    "${local.telegram_repo_root}/src/kb/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
  )
  telegram_lambda_hash = sha256(join("", concat(
    [
      filesha256("${local.telegram_lambda_dir}/handler.py"),
      filesha256("${local.telegram_lambda_dir}/start_handler.py"),
      filesha256("${local.telegram_lambda_dir}/invitation_commands.py"),
      filesha256("${local.telegram_lambda_dir}/kb_prefetch.py"),
      filesha256("${local.telegram_lambda_dir}/requirements.txt"),
      filesha256("${path.module}/bin/build-telegram-lambda.sh"),
    ],
    [for p in local.telegram_src_files : filesha256(p)],
  )))
}

resource "null_resource" "telegram_lambda_package" {
  triggers = {
    hash = local.telegram_lambda_hash
  }

  provisioner "local-exec" {
    command     = "${path.module}/bin/build-telegram-lambda.sh ${local.telegram_lambda_dir} ${local.telegram_lambda_zip}"
    interpreter = ["bash", "-c"]
  }
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "telegram_webhook" {
  name               = "prode-telegram-webhook-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "telegram_webhook_logs" {
  role       = aws_iam_role.telegram_webhook.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "telegram_webhook_inline" {
  statement {
    sid = "DynamoDBGSI"
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

  statement {
    sid       = "TelegramSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.telegram_secret_arn]
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

resource "aws_iam_role_policy" "telegram_webhook" {
  name   = "inline"
  role   = aws_iam_role.telegram_webhook.id
  policy = data.aws_iam_policy_document.telegram_webhook_inline.json
}

resource "aws_lambda_function" "telegram_webhook" {
  function_name = "prode-telegram-webhook-${var.env}"
  role          = aws_iam_role.telegram_webhook.arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  timeout       = 60
  memory_size   = 256

  filename         = local.telegram_lambda_zip
  source_code_hash = local.telegram_lambda_hash

  environment {
    variables = merge(
      {
        DYNAMODB_TABLE              = module.prode_table.dynamodb_table_id
        # invoke_agent_runtime espera el ARN del runtime, no del endpoint (qualifier=LIVE).
        AGENTCORE_RUNTIME_ARN       = aws_bedrockagentcore_agent_runtime.prode.agent_runtime_arn
        AGENTCORE_RUNTIME_QUALIFIER = aws_bedrockagentcore_agent_runtime_endpoint.live.name
        LOG_LEVEL                   = "INFO"
        TELEGRAM_SECRET_ID          = "SCALONIA_TELEGRAM_BOT_TOKEN"
        TELEGRAM_BOT_USERNAME       = var.telegram_bot_username
        INVITATION_NOTIFY_QUEUE_URL = var.enable_invitation_notify_queue ? aws_sqs_queue.invitation_exhausted[0].url : ""
      },
      module.kb.kb_query_lambda_name != "" ? {
        KB_QUERY_LAMBDA_NAME = module.kb.kb_query_lambda_name
      } : {},
    )
  }

  depends_on = [
    null_resource.telegram_lambda_package,
    aws_bedrockagentcore_agent_runtime_endpoint.live,
    module.kb,
  ]
}

resource "aws_apigatewayv2_api" "http" {
  name          = "prode-http-${var.env}"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_integration" "telegram" {
  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri          = aws_lambda_function.telegram_webhook.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "telegram" {
  api_id    = aws_apigatewayv2_api.http.id
  route_key = "POST /webhook/telegram"
  target    = "integrations/${aws_apigatewayv2_integration.telegram.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.http.id
  name        = "$default"
  auto_deploy = true
}

resource "aws_lambda_permission" "apigw_telegram" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.telegram_webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}
