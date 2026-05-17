output "guardrail_id" {
  description = "Bedrock Guardrail ID — referenciado por agentcore.json vía SSM"
  value       = aws_bedrock_guardrail.prode.guardrail_id
}

output "guardrail_version" {
  description = "Versión publicada del guardrail (Converse / AgentCore)"
  value       = aws_bedrock_guardrail_version.prode.version
}

output "guardrail_arn" {
  value = aws_bedrock_guardrail.prode.guardrail_arn
}

output "ssm_guardrail_id_name" {
  value = aws_ssm_parameter.guardrail_id.name
}

output "ssm_guardrail_version_name" {
  value = aws_ssm_parameter.guardrail_version.name
}
