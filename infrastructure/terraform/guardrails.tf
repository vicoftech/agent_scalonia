# SPEC-2026-015 — módulo guardrails (ver guardrails/main.tf)

moved {
  from = aws_bedrock_guardrail.prode
  to   = module.guardrails.aws_bedrock_guardrail.prode
}

moved {
  from = aws_bedrock_guardrail_version.prode
  to   = module.guardrails.aws_bedrock_guardrail_version.prode
}

module "guardrails" {
  source = "./guardrails"

  env            = var.env
  project_name   = var.project_name
  sns_alerts_arn = var.sns_alerts_arn
}
