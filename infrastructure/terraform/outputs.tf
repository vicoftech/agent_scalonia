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
