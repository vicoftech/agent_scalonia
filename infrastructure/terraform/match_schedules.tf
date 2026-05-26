# SPEC-2026-032 — EventBridge Scheduler por partido + Lambdas lifecycle

variable "enable_match_schedules" {
  type        = bool
  default     = false
  description = "Lambdas trivia/reminder/veda/scoring + Scheduler group + rol invoke. Requiere enable_result_queues para notify."
}

locals {
  lifecycle_lambda_names = toset([
    "trivia_pre_match",
    "match_reminder",
    "veda_activator",
    "scoring_processor",
  ])
  lifecycle_lambda_dirs = {
    trivia_pre_match   = "${path.module}/../lambdas/trivia_pre_match_dispatcher"
    match_reminder     = "${path.module}/../lambdas/match_reminder_dispatcher"
    veda_activator     = "${path.module}/../lambdas/veda_activator"
    scoring_processor  = "${path.module}/../lambdas/scoring_processor"
  }
  lifecycle_repo_root = abspath("${path.module}/../..")
  lifecycle_src_files = concat(
    [for f in sort(fileset("${local.lifecycle_repo_root}/src/dao", "**")) :
    "${local.lifecycle_repo_root}/src/dao/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.lifecycle_repo_root}/src/services", "**")) :
    "${local.lifecycle_repo_root}/src/services/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.lifecycle_repo_root}/src/models", "**")) :
    "${local.lifecycle_repo_root}/src/models/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.lifecycle_repo_root}/src/clients", "**")) :
    "${local.lifecycle_repo_root}/src/clients/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.lifecycle_repo_root}/src/scoring", "**")) :
    "${local.lifecycle_repo_root}/src/scoring/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.lifecycle_repo_root}/src/fixtures", "**")) :
    "${local.lifecycle_repo_root}/src/fixtures/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
    [for f in sort(fileset("${local.lifecycle_repo_root}/src/jobs", "**")) :
    "${local.lifecycle_repo_root}/src/jobs/${f}" if !endswith(f, "/") && !strcontains(f, "__pycache__")],
  )
  lifecycle_zip = {
    for name in local.lifecycle_lambda_names :
    name => "${path.module}/.build/${name}.zip"
  }
  lifecycle_hash = {
    for name in local.lifecycle_lambda_names :
    name => sha256(join("", concat(
      [filesha256("${path.module}/bin/build-lifecycle-lambda.sh")],
      [filesha256("${local.lifecycle_lambda_dirs[name]}/requirements.txt")],
      [for f in sort(fileset(local.lifecycle_lambda_dirs[name], "*.py")) :
      filesha256("${local.lifecycle_lambda_dirs[name]}/${f}")],
      [for p in local.lifecycle_src_files : filesha256(p)],
    )))
  }
  scheduler_group_name = "prode-match-${var.env}"
  notify_queue_url     = var.enable_result_queues ? aws_sqs_queue.match_notifications[0].url : ""
  scoring_queue_url    = var.enable_result_queues ? aws_sqs_queue.scoring[0].url : ""
}

# Gate: depends_on no admite ternarios; solo cuando OIDC + schedules están activos.
resource "null_resource" "scheduler_github_iam_gate" {
  count = var.enable_match_schedules && var.enable_github_oidc ? 1 : 0

  depends_on = [aws_iam_role_policy.github_actions_deploy]
}

resource "aws_scheduler_schedule_group" "match_lifecycle" {
  count = var.enable_match_schedules ? 1 : 0

  name = local.scheduler_group_name

  depends_on = [null_resource.scheduler_github_iam_gate]
}

data "aws_iam_policy_document" "scheduler_assume" {
  count = var.enable_match_schedules ? 1 : 0

  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler_invoke" {
  count = var.enable_match_schedules ? 1 : 0

  name               = "prode-scheduler-invoke-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume[0].json
}

data "aws_iam_policy_document" "scheduler_invoke_lambdas" {
  count = var.enable_match_schedules ? 1 : 0

  statement {
    sid     = "InvokeLifecycleLambdas"
    actions = ["lambda:InvokeFunction"]
    resources = [
      aws_lambda_function.trivia_pre_match[0].arn,
      aws_lambda_function.match_reminder[0].arn,
      aws_lambda_function.veda_activator[0].arn,
      aws_lambda_function.scoring_processor[0].arn,
    ]
  }

  dynamic "statement" {
    for_each = var.enable_result_collector ? [1] : []
    content {
      sid       = "InvokeResultCollector"
      actions   = ["lambda:InvokeFunction"]
      resources = [aws_lambda_function.result_collector[0].arn]
    }
  }
}

resource "aws_iam_role_policy" "scheduler_invoke" {
  count = var.enable_match_schedules ? 1 : 0

  name   = "scheduler-invoke-lambdas"
  role   = aws_iam_role.scheduler_invoke[0].id
  policy = data.aws_iam_policy_document.scheduler_invoke_lambdas[0].json
}

resource "null_resource" "lifecycle_lambda_package" {
  for_each = var.enable_match_schedules ? local.lifecycle_lambda_names : toset([])

  triggers = {
    hash = local.lifecycle_hash[each.key]
  }

  provisioner "local-exec" {
    command     = "${path.module}/bin/build-lifecycle-lambda.sh ${local.lifecycle_lambda_dirs[each.key]} ${local.lifecycle_zip[each.key]}"
    interpreter = ["bash", "-c"]
  }
}

data "aws_iam_policy_document" "lifecycle_lambda_inline" {
  count = var.enable_match_schedules ? 1 : 0

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
      sid       = "SQSSend"
      actions   = ["sqs:SendMessage"]
      resources = [
        aws_sqs_queue.match_notifications[0].arn,
        aws_sqs_queue.scoring[0].arn,
      ]
    }
  }

  statement {
    sid       = "TelegramSecret"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.telegram_secret_arn]
  }
}

resource "aws_iam_role" "lifecycle_lambda" {
  for_each = var.enable_match_schedules ? local.lifecycle_lambda_names : toset([])

  name               = "prode-${replace(each.key, "_", "-")}-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "lifecycle_lambda_logs" {
  for_each = var.enable_match_schedules ? local.lifecycle_lambda_names : toset([])

  role       = aws_iam_role.lifecycle_lambda[each.key].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "lifecycle_lambda" {
  for_each = var.enable_match_schedules ? local.lifecycle_lambda_names : toset([])

  name   = "${each.key}-inline"
  role   = aws_iam_role.lifecycle_lambda[each.key].id
  policy = data.aws_iam_policy_document.lifecycle_lambda_inline[0].json
}

data "aws_iam_policy_document" "scoring_processor_sqs_consume" {
  count = var.enable_match_schedules && var.enable_result_queues ? 1 : 0

  statement {
    sid = "SQSConsumeScoring"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes",
      "sqs:ChangeMessageVisibility",
    ]
    resources = [aws_sqs_queue.scoring[0].arn]
  }
}

resource "aws_iam_role_policy" "scoring_processor_sqs_consume" {
  count = var.enable_match_schedules && var.enable_result_queues ? 1 : 0

  name   = "scoring-processor-sqs-consume"
  role   = aws_iam_role.lifecycle_lambda["scoring_processor"].id
  policy = data.aws_iam_policy_document.scoring_processor_sqs_consume[0].json
}

resource "aws_lambda_function" "trivia_pre_match" {
  count = var.enable_match_schedules ? 1 : 0

  function_name = "prode-trivia-pre-match-${var.env}"
  role          = aws_iam_role.lifecycle_lambda["trivia_pre_match"].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  timeout       = 120
  memory_size   = 512

  filename         = local.lifecycle_zip["trivia_pre_match"]
  source_code_hash = local.lifecycle_hash["trivia_pre_match"]

  environment {
    variables = {
      DYNAMODB_TABLE      = module.prode_table.dynamodb_table_id
      TELEGRAM_SECRET_ARN = var.telegram_secret_arn
      LOG_LEVEL           = "INFO"
    }
  }

  depends_on = [null_resource.lifecycle_lambda_package["trivia_pre_match"]]
}

resource "aws_lambda_function" "match_reminder" {
  count = var.enable_match_schedules ? 1 : 0

  function_name = "prode-match-reminder-${var.env}"
  role          = aws_iam_role.lifecycle_lambda["match_reminder"].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  timeout       = 60
  memory_size   = 256

  filename         = local.lifecycle_zip["match_reminder"]
  source_code_hash = local.lifecycle_hash["match_reminder"]

  environment {
    variables = {
      DYNAMODB_TABLE          = module.prode_table.dynamodb_table_id
      NOTIFICATION_QUEUE_URL  = local.notify_queue_url
      TELEGRAM_SECRET_ARN     = var.telegram_secret_arn
      LOG_LEVEL               = "INFO"
    }
  }

  depends_on = [null_resource.lifecycle_lambda_package["match_reminder"]]
}

resource "aws_lambda_function" "veda_activator" {
  count = var.enable_match_schedules ? 1 : 0

  function_name = "prode-veda-activator-${var.env}"
  role          = aws_iam_role.lifecycle_lambda["veda_activator"].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  timeout       = 60
  memory_size   = 256

  filename         = local.lifecycle_zip["veda_activator"]
  source_code_hash = local.lifecycle_hash["veda_activator"]

  environment {
    variables = {
      DYNAMODB_TABLE          = module.prode_table.dynamodb_table_id
      NOTIFICATION_QUEUE_URL  = local.notify_queue_url
      TELEGRAM_SECRET_ARN     = var.telegram_secret_arn
      LOG_LEVEL               = "INFO"
    }
  }

  depends_on = [null_resource.lifecycle_lambda_package["veda_activator"]]
}

resource "aws_lambda_function" "scoring_processor" {
  count = var.enable_match_schedules ? 1 : 0

  function_name = "prode-scoring-processor-${var.env}"
  role          = aws_iam_role.lifecycle_lambda["scoring_processor"].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  timeout       = 120
  memory_size   = 512

  filename         = local.lifecycle_zip["scoring_processor"]
  source_code_hash = local.lifecycle_hash["scoring_processor"]

  environment {
    variables = {
      DYNAMODB_TABLE          = module.prode_table.dynamodb_table_id
      NOTIFICATION_QUEUE_URL  = local.notify_queue_url
      TELEGRAM_SECRET_ARN     = var.telegram_secret_arn
      LOG_LEVEL               = "INFO"
    }
  }

  depends_on = [null_resource.lifecycle_lambda_package["scoring_processor"]]
}

resource "aws_lambda_event_source_mapping" "scoring_queue" {
  count = var.enable_match_schedules && var.enable_result_queues ? 1 : 0

  event_source_arn = aws_sqs_queue.scoring[0].arn
  function_name    = aws_lambda_function.scoring_processor[0].arn
  batch_size       = 5
  enabled          = true

  function_response_types = ["ReportBatchItemFailures"]
}

resource "aws_lambda_permission" "scoring_sqs" {
  count = var.enable_match_schedules && var.enable_result_queues ? 1 : 0

  statement_id  = "AllowSQSTrigger"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scoring_processor[0].function_name
  principal     = "sqs.amazonaws.com"
  source_arn    = aws_sqs_queue.scoring[0].arn
}

locals {
  scheduler_target_arns = var.enable_match_schedules ? {
    trivia_pre_match   = aws_lambda_function.trivia_pre_match[0].arn
    match_reminder     = aws_lambda_function.match_reminder[0].arn
    veda_activator     = aws_lambda_function.veda_activator[0].arn
    scoring_processor  = aws_lambda_function.scoring_processor[0].arn
    result_collector   = var.enable_result_collector ? aws_lambda_function.result_collector[0].arn : ""
  } : {}
}

resource "aws_lambda_permission" "scheduler_trivia" {
  count = var.enable_match_schedules ? 1 : 0

  statement_id  = "AllowScheduler"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.trivia_pre_match[0].function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "${aws_scheduler_schedule_group.match_lifecycle[0].arn}/*"
}

resource "aws_lambda_permission" "scheduler_reminder" {
  count = var.enable_match_schedules ? 1 : 0

  statement_id  = "AllowScheduler"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.match_reminder[0].function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "${aws_scheduler_schedule_group.match_lifecycle[0].arn}/*"
}

resource "aws_lambda_permission" "scheduler_veda" {
  count = var.enable_match_schedules ? 1 : 0

  statement_id  = "AllowScheduler"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.veda_activator[0].function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "${aws_scheduler_schedule_group.match_lifecycle[0].arn}/*"
}

resource "aws_lambda_permission" "scheduler_scoring" {
  count = var.enable_match_schedules ? 1 : 0

  statement_id  = "AllowScheduler"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scoring_processor[0].function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "${aws_scheduler_schedule_group.match_lifecycle[0].arn}/*"
}

resource "aws_lambda_permission" "scheduler_result" {
  count = var.enable_match_schedules && var.enable_result_collector ? 1 : 0

  statement_id  = "AllowSchedulerMatchEnded"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.result_collector[0].function_name
  principal     = "scheduler.amazonaws.com"
  source_arn    = "${aws_scheduler_schedule_group.match_lifecycle[0].arn}/*"
}

output "match_scheduler_group_name" {
  value       = try(local.scheduler_group_name, null)
  description = "EventBridge Scheduler group — SCHEDULER_GROUP_NAME"
}

output "match_scheduler_invoke_role_arn" {
  value       = try(aws_iam_role.scheduler_invoke[0].arn, null)
  description = "Rol para targets Scheduler — SCHEDULER_INVOKE_ROLE_ARN"
}

output "match_schedule_lambda_arns" {
  value = var.enable_match_schedules ? {
    trivia_pre_match   = aws_lambda_function.trivia_pre_match[0].arn
    match_reminder     = aws_lambda_function.match_reminder[0].arn
    veda_activator     = aws_lambda_function.veda_activator[0].arn
    result_collector   = var.enable_result_collector ? aws_lambda_function.result_collector[0].arn : null
    scoring_processor  = aws_lambda_function.scoring_processor[0].arn
  } : null
  description = "ARNs para LAMBDA_ARN_* en scripts/provision_match_schedules.py"
}
