# SPEC-2026-031 — SQS match_notifications → Telegram sendMessage

locals {
  match_notify_lambda_dir = "${path.module}/../lambdas/match_notify_dispatcher"
  match_notify_zip        = "${path.module}/.build/match_notify_dispatcher.zip"
  match_notify_repo_root  = abspath("${path.module}/../..")
  match_notify_src_files = concat(
    [for f in sort(fileset("${local.match_notify_repo_root}/src/dao", "**")) :
    "${local.match_notify_repo_root}/src/dao/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.match_notify_repo_root}/src/services", "**")) :
    "${local.match_notify_repo_root}/src/services/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.match_notify_repo_root}/src/clients", "**")) :
    "${local.match_notify_repo_root}/src/clients/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
  )
  match_notify_py_files = sort(fileset("${local.match_notify_lambda_dir}", "*.py"))
  match_notify_hash = sha256(join("", concat(
    [
      filesha256("${path.module}/bin/build-match-notify-dispatcher-lambda.sh"),
      filesha256("${local.match_notify_lambda_dir}/requirements.txt"),
    ],
    [for f in local.match_notify_py_files : filesha256("${local.match_notify_lambda_dir}/${f}")],
    [for p in local.match_notify_src_files : filesha256(p)],
  )))
}

resource "aws_sqs_queue_policy" "match_notifications" {
  count = var.enable_result_queues && var.enable_result_collector ? 1 : 0

  queue_url = aws_sqs_queue.match_notifications[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.match_notifications[0].arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = [aws_lambda_function.result_collector[0].arn]
        }
      }
    }]
  })
}

resource "null_resource" "match_notify_dispatcher_package" {
  count = var.enable_result_queues ? 1 : 0

  triggers = {
    hash = local.match_notify_hash
  }

  provisioner "local-exec" {
    command     = "${path.module}/bin/build-match-notify-dispatcher-lambda.sh ${local.match_notify_lambda_dir} ${local.match_notify_zip}"
    interpreter = ["bash", "-c"]
  }
}

resource "aws_iam_role" "match_notify_dispatcher" {
  count = var.enable_result_queues ? 1 : 0

  name               = "prode-match-notify-dispatcher-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "match_notify_dispatcher_logs" {
  count = var.enable_result_queues ? 1 : 0

  role       = aws_iam_role.match_notify_dispatcher[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "match_notify_dispatcher_inline" {
  count = var.enable_result_queues ? 1 : 0

  statement {
    sid = "DynamoDBRead"
    actions = [
      "dynamodb:GetItem",
    ]
    resources = [
      module.prode_table.dynamodb_table_arn,
    ]
  }

  statement {
    sid = "SQSConsume"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [aws_sqs_queue.match_notifications[0].arn]
  }

  statement {
    sid       = "TelegramSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.telegram_secret_arn]
  }
}

resource "aws_iam_role_policy" "match_notify_dispatcher" {
  count = var.enable_result_queues ? 1 : 0

  name   = "match-notify-dispatcher-inline"
  role   = aws_iam_role.match_notify_dispatcher[0].id
  policy = data.aws_iam_policy_document.match_notify_dispatcher_inline[0].json
}

resource "aws_lambda_function" "match_notify_dispatcher" {
  count = var.enable_result_queues ? 1 : 0

  function_name = "prode-match-notify-dispatcher-${var.env}"
  role          = aws_iam_role.match_notify_dispatcher[0].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  timeout       = 60
  memory_size   = 256

  filename         = local.match_notify_zip
  source_code_hash = local.match_notify_hash

  environment {
    variables = {
      DYNAMODB_TABLE     = module.prode_table.dynamodb_table_id
      TELEGRAM_SECRET_ARN = var.telegram_secret_arn
      LOG_LEVEL          = "INFO"
    }
  }

  depends_on = [null_resource.match_notify_dispatcher_package]
}

resource "aws_lambda_event_source_mapping" "match_notifications" {
  count = var.enable_result_queues ? 1 : 0

  event_source_arn = aws_sqs_queue.match_notifications[0].arn
  function_name    = aws_lambda_function.match_notify_dispatcher[0].arn
  batch_size       = 10
  enabled          = true

  function_response_types = ["ReportBatchItemFailures"]
}

resource "aws_lambda_permission" "match_notify_sqs" {
  count = var.enable_result_queues ? 1 : 0

  statement_id  = "AllowSQSTrigger"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.match_notify_dispatcher[0].function_name
  principal     = "sqs.amazonaws.com"
  source_arn    = aws_sqs_queue.match_notifications[0].arn
}
