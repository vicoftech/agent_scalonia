# Lambda Telegram + HTTP API POST /webhook/telegram — TASK-000-004

variable "telegram_secret_arn" {
  type        = string
  description = "ARN del secreto TELEGRAM_BOT_TOKEN en Secrets Manager."
}

variable "agentcore_agent_id" {
  type        = string
  description = "ID del agente Bedrock AgentCore (invoke_agent)."
}

data "archive_file" "telegram_webhook_zip" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/telegram_webhook/handler.py"
  output_path = "${path.module}/.build/telegram_webhook.zip"
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
      "dynamodb:Query",
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

  statement {
    sid       = "BedrockInvokeAgent"
    actions   = ["bedrock:InvokeAgent"]
    resources = ["*"]
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

  filename         = data.archive_file.telegram_webhook_zip.output_path
  source_code_hash = data.archive_file.telegram_webhook_zip.output_base64sha256

  environment {
    variables = {
      DYNAMODB_TABLE        = module.prode_table.dynamodb_table_id
      AGENTCORE_AGENT_ID    = var.agentcore_agent_id
      AGENTCORE_AGENT_ALIAS = "LIVE"
      AWS_REGION            = var.aws_region
      LOG_LEVEL             = "INFO"
    }
  }
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
