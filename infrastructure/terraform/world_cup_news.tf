# SPEC-2026-046 — World Cup News (Telegram broadcast + redirect)

variable "enable_world_cup_news" {
  type        = bool
  default     = false
  description = "Lambda noticias + cron PRE 11/17 ART + poller LIVE 5 min + redirect lecturas."
}

resource "random_password" "news_redirect_secret" {
  count   = var.enable_world_cup_news ? 1 : 0
  length  = 32
  special = false
}

locals {
  world_cup_news_lambda_dir = "${path.module}/../lambdas/world_cup_news"
  world_cup_news_zip        = "${path.module}/.build/world_cup_news.zip"
  news_redirect_lambda_dir  = "${path.module}/../lambdas/news_redirect"
  news_redirect_zip         = "${path.module}/.build/news_redirect.zip"
  world_cup_news_repo_root  = abspath("${path.module}/../..")
  world_cup_news_src_files = concat(
    [for f in sort(fileset("${local.world_cup_news_repo_root}/src/dao", "**")) :
    "${local.world_cup_news_repo_root}/src/dao/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.world_cup_news_repo_root}/src/services", "**")) :
    "${local.world_cup_news_repo_root}/src/services/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.world_cup_news_repo_root}/src/jobs", "**")) :
    "${local.world_cup_news_repo_root}/src/jobs/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.world_cup_news_repo_root}/src/web", "**")) :
    "${local.world_cup_news_repo_root}/src/web/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.world_cup_news_repo_root}/src/clients", "**")) :
    "${local.world_cup_news_repo_root}/src/clients/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
  )
  world_cup_news_py_files = sort(fileset("${local.world_cup_news_lambda_dir}", "*.py"))
  world_cup_news_hash = sha256(join("", concat(
    [
      filesha256("${path.module}/bin/build-world-cup-news-lambda.sh"),
      filesha256("${local.world_cup_news_lambda_dir}/requirements.txt"),
    ],
    [for f in local.world_cup_news_py_files : filesha256("${local.world_cup_news_lambda_dir}/${f}")],
    [for p in local.world_cup_news_src_files : filesha256(p)],
  )))
  news_redirect_py_files = sort(fileset("${local.news_redirect_lambda_dir}", "*.py"))
  news_redirect_hash = sha256(join("", concat(
    [
      filesha256("${path.module}/bin/build-news-redirect-lambda.sh"),
      filesha256("${local.news_redirect_lambda_dir}/requirements.txt"),
    ],
    [for f in local.news_redirect_py_files : filesha256("${local.news_redirect_lambda_dir}/${f}")],
    [for p in local.world_cup_news_src_files : filesha256(p)],
  )))
  news_redirect_base_url = trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")
}

resource "null_resource" "world_cup_news_package" {
  count = var.enable_world_cup_news ? 1 : 0

  triggers = {
    hash = local.world_cup_news_hash
  }

  provisioner "local-exec" {
    command     = "${path.module}/bin/build-world-cup-news-lambda.sh ${local.world_cup_news_lambda_dir} ${local.world_cup_news_zip}"
    interpreter = ["bash", "-c"]
  }
}

resource "null_resource" "news_redirect_package" {
  count = var.enable_world_cup_news ? 1 : 0

  triggers = {
    hash = local.news_redirect_hash
  }

  provisioner "local-exec" {
    command     = "${path.module}/bin/build-news-redirect-lambda.sh ${local.news_redirect_lambda_dir} ${local.news_redirect_zip}"
    interpreter = ["bash", "-c"]
  }
}

resource "aws_iam_role" "world_cup_news" {
  count = var.enable_world_cup_news ? 1 : 0

  name               = "prode-world-cup-news-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "world_cup_news_logs" {
  count = var.enable_world_cup_news ? 1 : 0

  role       = aws_iam_role.world_cup_news[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "world_cup_news_inline" {
  count = var.enable_world_cup_news ? 1 : 0

  statement {
    sid = "ProdeTable"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Scan",
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

  dynamic "statement" {
    for_each = var.tavily_secret_arn != "" ? [1] : []
    content {
      sid       = "TavilySecret"
      actions   = ["secretsmanager:GetSecretValue"]
      resources = [var.tavily_secret_arn]
    }
  }
}

resource "aws_iam_role_policy" "world_cup_news" {
  count = var.enable_world_cup_news ? 1 : 0

  name   = "inline"
  role   = aws_iam_role.world_cup_news[0].id
  policy = data.aws_iam_policy_document.world_cup_news_inline[0].json
}

resource "aws_lambda_function" "world_cup_news" {
  count = var.enable_world_cup_news ? 1 : 0

  function_name = "prode-world-cup-news-${var.env}"
  role          = aws_iam_role.world_cup_news[0].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  timeout       = 300
  memory_size   = 512

  filename         = local.world_cup_news_zip
  source_code_hash = local.world_cup_news_hash

  environment {
    variables = merge(
      {
        DYNAMODB_TABLE         = module.prode_table.dynamodb_table_id
        ENV                    = var.env
        ENABLE_WORLD_CUP_NEWS  = "true"
        TELEGRAM_SECRET_ARN    = var.telegram_secret_arn
        NEWS_REDIRECT_BASE_URL = local.news_redirect_base_url
        NEWS_REDIRECT_SECRET   = random_password.news_redirect_secret[0].result
      },
      var.tavily_secret_arn != "" ? { TAVILY_SECRET_ARN = var.tavily_secret_arn } : {},
    )
  }

  tags = {
    Project = "prode-mundial"
    Env     = var.env
    Spec    = "SPEC-2026-046"
  }

  depends_on = [null_resource.world_cup_news_package]
}

resource "aws_iam_role" "news_redirect" {
  count = var.enable_world_cup_news ? 1 : 0

  name               = "prode-news-redirect-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "news_redirect_logs" {
  count = var.enable_world_cup_news ? 1 : 0

  role       = aws_iam_role.news_redirect[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "news_redirect_inline" {
  count = var.enable_world_cup_news ? 1 : 0

  statement {
    sid = "ProdeTable"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
    ]
    resources = [module.prode_table.dynamodb_table_arn]
  }
}

resource "aws_iam_role_policy" "news_redirect" {
  count = var.enable_world_cup_news ? 1 : 0

  name   = "inline"
  role   = aws_iam_role.news_redirect[0].id
  policy = data.aws_iam_policy_document.news_redirect_inline[0].json
}

resource "aws_lambda_function" "news_redirect" {
  count = var.enable_world_cup_news ? 1 : 0

  function_name = "prode-news-redirect-${var.env}"
  role          = aws_iam_role.news_redirect[0].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  timeout       = 10
  memory_size   = 128

  filename         = local.news_redirect_zip
  source_code_hash = local.news_redirect_hash

  environment {
    variables = {
      DYNAMODB_TABLE       = module.prode_table.dynamodb_table_id
      ENV                  = var.env
      NEWS_REDIRECT_SECRET = random_password.news_redirect_secret[0].result
    }
  }

  tags = {
    Project = "prode-mundial"
    Env     = var.env
    Spec    = "SPEC-2026-046"
  }

  depends_on = [null_resource.news_redirect_package]
}

resource "aws_apigatewayv2_integration" "news_redirect" {
  count = var.enable_world_cup_news ? 1 : 0

  api_id                 = aws_apigatewayv2_api.http.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.news_redirect[0].invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "news_redirect" {
  count = var.enable_world_cup_news ? 1 : 0

  api_id    = aws_apigatewayv2_api.http.id
  route_key = "GET /news/r/{news_id}"
  target    = "integrations/${aws_apigatewayv2_integration.news_redirect[0].id}"
}

resource "aws_lambda_permission" "apigw_news_redirect" {
  count = var.enable_world_cup_news ? 1 : 0

  statement_id  = "AllowAPIGatewayNewsRedirect"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.news_redirect[0].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.http.execution_arn}/*/*"
}

data "aws_iam_policy_document" "scheduler_world_cup_news_assume" {
  count = var.enable_world_cup_news ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler_world_cup_news" {
  count = var.enable_world_cup_news ? 1 : 0

  name               = "prode-scheduler-world-cup-news-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.scheduler_world_cup_news_assume[0].json
}

resource "aws_iam_role_policy" "scheduler_world_cup_news_invoke" {
  count = var.enable_world_cup_news ? 1 : 0

  name = "invoke-lambda"
  role = aws_iam_role.scheduler_world_cup_news[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.world_cup_news[0].arn
    }]
  })
}

resource "aws_scheduler_schedule" "wc_news_pre_morning" {
  count = var.enable_world_cup_news ? 1 : 0

  name       = "wc-news-pre-morning-${var.env}"
  group_name = "default"

  schedule_expression          = "cron(0 11 * * ? *)"
  schedule_expression_timezone = "America/Argentina/Buenos_Aires"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.world_cup_news[0].arn
    role_arn = aws_iam_role.scheduler_world_cup_news[0].arn
    input    = jsonencode({ phase = "PRE", slot = "MORNING" })
  }
}

resource "aws_scheduler_schedule" "wc_news_pre_evening" {
  count = var.enable_world_cup_news ? 1 : 0

  name       = "wc-news-pre-evening-${var.env}"
  group_name = "default"

  schedule_expression          = "cron(0 17 * * ? *)"
  schedule_expression_timezone = "America/Argentina/Buenos_Aires"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.world_cup_news[0].arn
    role_arn = aws_iam_role.scheduler_world_cup_news[0].arn
    input    = jsonencode({ phase = "PRE", slot = "EVENING" })
  }
}

resource "aws_lambda_permission" "scheduler_wc_news_pre_morning" {
  count = var.enable_world_cup_news ? 1 : 0

  statement_id  = "AllowSchedulerMorning"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.world_cup_news[0].function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.wc_news_pre_morning[0].arn
}

resource "aws_lambda_permission" "scheduler_wc_news_pre_evening" {
  count = var.enable_world_cup_news ? 1 : 0

  statement_id  = "AllowSchedulerEvening"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.world_cup_news[0].function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = aws_scheduler_schedule.wc_news_pre_evening[0].arn
}

resource "aws_cloudwatch_event_rule" "world_cup_news_live" {
  count = var.enable_world_cup_news ? 1 : 0

  name                = "prode-world-cup-news-live-${var.env}"
  description         = "SPEC-046 — ventanas PRE/POST partido"
  schedule_expression = "rate(5 minutes)"
}

resource "aws_cloudwatch_event_target" "world_cup_news_live" {
  count = var.enable_world_cup_news ? 1 : 0

  rule      = aws_cloudwatch_event_rule.world_cup_news_live[0].name
  target_id = "world-cup-news-live"
  arn       = aws_lambda_function.world_cup_news[0].arn
  input     = jsonencode({ job = "live_poll", phase = "LIVE" })
}

resource "aws_lambda_permission" "world_cup_news_live_eventbridge" {
  count = var.enable_world_cup_news ? 1 : 0

  statement_id  = "AllowEventBridgeLive"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.world_cup_news[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.world_cup_news_live[0].arn
}

output "world_cup_news_lambda" {
  value = var.enable_world_cup_news ? aws_lambda_function.world_cup_news[0].function_name : null
}

output "news_redirect_base_url" {
  value = var.enable_world_cup_news ? local.news_redirect_base_url : null
}
