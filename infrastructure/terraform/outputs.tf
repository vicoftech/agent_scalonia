output "dynamodb_table_name" {
  description = "DynamoDB ProdeTable name — env vars / Lambdas"
  value       = module.prode_table.dynamodb_table_id
}

output "dynamodb_table_arn" {
  description = "DynamoDB table ARN — políticas IAM"
  value       = module.prode_table.dynamodb_table_arn
}

output "dynamodb_stream_arn" {
  description = "Stream ARN — trigger Lambda sync_dynamo_to_aurora"
  value       = module.prode_table.dynamodb_table_stream_arn
}

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID"
  value       = aws_cognito_user_pool.prode.id
}

output "cognito_user_pool_arn" {
  description = "Cognito User Pool ARN"
  value       = aws_cognito_user_pool.prode.arn
}

output "cognito_app_client_id" {
  description = "App client sin secret (público)"
  value       = aws_cognito_user_pool_client.prode_app.id
}

# --- Aurora existente (data source) ---

output "aurora_cluster_endpoint" {
  description = "Writer endpoint del cluster (vacío si aurora_cluster_identifier no está definido)"
  value       = try(data.aws_rds_cluster.prode[0].endpoint, null)
}

output "aurora_cluster_reader_endpoint" {
  description = "Reader endpoint del cluster"
  value       = try(data.aws_rds_cluster.prode[0].reader_endpoint, null)
}

output "aurora_cluster_port" {
  value = try(data.aws_rds_cluster.prode[0].port, null)
}

output "aurora_cluster_resource_id" {
  description = "DbClusterResourceId (p. ej. para Policy IAM / Proxy)"
  value       = try(data.aws_rds_cluster.prode[0].cluster_resource_id, null)
}

# --- Telegram webhook ---

output "telegram_webhook_url" {
  description = "URL para setWebhook de Telegram"
  value       = "${trimsuffix(aws_apigatewayv2_stage.default.invoke_url, "/")}/webhook/telegram"
}

output "telegram_lambda_function_name" {
  value = aws_lambda_function.telegram_webhook.function_name
}

# --- AgentCore Runtime (Terraform) ---

output "agent_runtime_id" {
  description = "ID del AgentCore Runtime"
  value       = aws_bedrockagentcore_agent_runtime.prode.agent_runtime_id
}

output "agent_runtime_arn" {
  description = "ARN del AgentCore Runtime"
  value       = aws_bedrockagentcore_agent_runtime.prode.agent_runtime_arn
}

output "agent_runtime_endpoint_arn" {
  description = "ARN del endpoint LIVE — invocar con bedrock-agentcore:InvokeAgentRuntime"
  value       = aws_bedrockagentcore_agent_runtime_endpoint.live.agent_runtime_endpoint_arn
}

output "agent_code_s3_bucket" {
  value = aws_s3_bucket.agent_code.id
}
