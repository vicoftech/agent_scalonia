# SPEC-2026-041 — Lambda match_schedule_manager (schedules devfast-* en dev)

variable "enable_match_lifecycle_sandbox" {
  type        = bool
  default     = false
  description = "Lambda prode-match-schedule-manager — solo dev; requiere enable_match_schedules."
}

locals {
  sandbox_manager_enabled = (
    var.enable_match_lifecycle_sandbox
    && var.enable_match_schedules
    && !local.is_prod
  )
  sandbox_manager_dir = "${path.module}/../lambdas/match_schedule_manager"
  sandbox_manager_zip = "${path.module}/.build/match_schedule_manager.zip"
  sandbox_manager_hash = sha256(join("", concat(
    [filesha256("${path.module}/bin/build-lifecycle-lambda.sh")],
    [filesha256("${local.sandbox_manager_dir}/requirements.txt")],
    [for f in sort(fileset(local.sandbox_manager_dir, "*.py")) :
    filesha256("${local.sandbox_manager_dir}/${f}")],
    [filesha256("${local.lifecycle_repo_root}/src/services/match_schedule_sandbox.py")],
    [filesha256("${local.lifecycle_repo_root}/src/services/scheduler_manager.py")],
    [for p in local.lifecycle_src_files : filesha256(p)],
  )))
}

resource "null_resource" "match_schedule_manager_package" {
  count = local.sandbox_manager_enabled ? 1 : 0

  triggers = { hash = local.sandbox_manager_hash }

  provisioner "local-exec" {
    command     = "${path.module}/bin/build-lifecycle-lambda.sh ${local.sandbox_manager_dir} ${local.sandbox_manager_zip}"
    interpreter = ["bash", "-c"]
  }
}

data "aws_iam_policy_document" "match_schedule_manager_inline" {
  count = local.sandbox_manager_enabled ? 1 : 0

  statement {
    sid = "DynamoDB"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
    ]
    resources = [
      module.prode_table.dynamodb_table_arn,
    ]
  }

  statement {
    sid = "EventBridgeScheduler"
    actions = [
      "scheduler:CreateSchedule",
      "scheduler:UpdateSchedule",
      "scheduler:DeleteSchedule",
      "scheduler:GetSchedule",
      "scheduler:ListSchedules",
    ]
    resources = [
      aws_scheduler_schedule_group.match_lifecycle[0].arn,
      "${aws_scheduler_schedule_group.match_lifecycle[0].arn}/*",
    ]
  }
}

resource "aws_iam_role" "match_schedule_manager" {
  count = local.sandbox_manager_enabled ? 1 : 0

  name               = "prode-match-schedule-manager-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
}

resource "aws_iam_role_policy_attachment" "match_schedule_manager_logs" {
  count = local.sandbox_manager_enabled ? 1 : 0

  role       = aws_iam_role.match_schedule_manager[0].name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "match_schedule_manager" {
  count = local.sandbox_manager_enabled ? 1 : 0

  name   = "match-schedule-manager-inline"
  role   = aws_iam_role.match_schedule_manager[0].id
  policy = data.aws_iam_policy_document.match_schedule_manager_inline[0].json
}

resource "aws_lambda_function" "match_schedule_manager" {
  count = local.sandbox_manager_enabled ? 1 : 0

  function_name = "prode-match-schedule-manager-${var.env}"
  role          = aws_iam_role.match_schedule_manager[0].arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  architectures = ["arm64"]
  timeout       = 60
  memory_size   = 256

  filename         = local.sandbox_manager_zip
  source_code_hash = local.sandbox_manager_hash

  environment {
    variables = {
      DYNAMODB_TABLE                  = module.prode_table.dynamodb_table_id
      ENV                             = var.env
      ENABLE_MATCH_LIFECYCLE_SANDBOX  = "true"
      ENABLE_MATCH_SCHEDULES          = "true"
      SCHEDULER_GROUP_NAME            = local.scheduler_group_name
      SCHEDULER_INVOKE_ROLE_ARN       = aws_iam_role.scheduler_invoke[0].arn
      LAMBDA_ARN_TRIVIA_PRE_MATCH     = aws_lambda_function.trivia_pre_match[0].arn
      LAMBDA_ARN_MATCH_REMINDER        = aws_lambda_function.match_reminder[0].arn
      LAMBDA_ARN_VEDA_ACTIVATOR       = aws_lambda_function.veda_activator[0].arn
      LAMBDA_ARN_RESULT_COLLECTOR      = var.enable_result_collector ? aws_lambda_function.result_collector[0].arn : ""
      LAMBDA_ARN_SCORING_PROCESSOR     = aws_lambda_function.scoring_processor[0].arn
      LOG_LEVEL                       = "INFO"
    }
  }

  depends_on = [null_resource.match_schedule_manager_package]
}

output "match_schedule_manager_function_name" {
  value       = try(aws_lambda_function.match_schedule_manager[0].function_name, null)
  description = "Lambda SPEC-041 provision/cancel devfast schedules"
}
