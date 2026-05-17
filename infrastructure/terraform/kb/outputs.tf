output "kb_s3_bucket" {
  value = aws_s3_bucket.kb_documents.id
}

output "kb_s3_bucket_arn" {
  value = aws_s3_bucket.kb_documents.arn
}

output "ssm_kb_s3_bucket_name" {
  value = aws_ssm_parameter.kb_s3_bucket.name
}

output "kb_query_lambda_name" {
  value = try(aws_lambda_function.kb_query[0].function_name, "")
}

output "kb_query_lambda_arn" {
  value = try(aws_lambda_function.kb_query[0].arn, "")
}

output "kb_ingest_lambda_name" {
  value = try(aws_lambda_function.kb_ingest[0].function_name, "")
}

output "kb_lambdas_enabled" {
  value = local.kb_lambda_enabled
}

output "aurora_sync_secret_arn" {
  value = local.aurora_secret_arn
}
