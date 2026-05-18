# SPEC-020-007 — notificación fire-and-forget cuando invitación → EXHAUSTED (opcional).

variable "enable_invitation_notify_queue" {
  type        = bool
  default     = false
  description = "Si true, crea cola SQS y expone INVITATION_NOTIFY_QUEUE_URL a Lambdas."
}

resource "aws_sqs_queue" "invitation_exhausted" {
  count = var.enable_invitation_notify_queue ? 1 : 0

  name                       = "prode-invitation-exhausted-${var.env}"
  message_retention_seconds  = 86400
  visibility_timeout_seconds = 60
}

resource "aws_sqs_queue_policy" "invitation_exhausted" {
  count = var.enable_invitation_notify_queue ? 1 : 0

  queue_url = aws_sqs_queue.invitation_exhausted[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.invitation_exhausted[0].arn
      Condition = {
        ArnEquals = {
          "aws:SourceArn" = [
            aws_lambda_function.telegram_webhook.arn,
          ]
        }
      }
    }]
  })
}

data "aws_iam_policy_document" "invitation_notify_sqs" {
  count = var.enable_invitation_notify_queue ? 1 : 0

  statement {
    sid       = "InvitationNotifySQS"
    actions   = ["sqs:SendMessage"]
    resources = [aws_sqs_queue.invitation_exhausted[0].arn]
  }
}

resource "aws_iam_role_policy" "telegram_invitation_notify" {
  count = var.enable_invitation_notify_queue ? 1 : 0

  name   = "invitation-notify-sqs"
  role   = aws_iam_role.telegram_webhook.id
  policy = data.aws_iam_policy_document.invitation_notify_sqs[0].json
}

resource "aws_iam_role_policy" "agent_invitation_notify" {
  count = var.enable_invitation_notify_queue ? 1 : 0

  name   = "invitation-notify-sqs"
  role   = aws_iam_role.agent_runtime.id
  policy = data.aws_iam_policy_document.invitation_notify_sqs[0].json
}
