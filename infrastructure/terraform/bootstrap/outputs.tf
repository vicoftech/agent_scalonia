output "state_bucket_name" {
  description = "Bucket S3 para terraform.tfstate"
  value       = aws_s3_bucket.terraform_state.id
}

output "lock_table_name" {
  description = "Tabla DynamoDB para lock de estado"
  value       = aws_dynamodb_table.terraform_lock.name
}

output "aws_region" {
  value = var.aws_region
}

output "terraform_state_bucket" {
  value = aws_s3_bucket.terraform_state.id
}

output "terraform_state_lock_table" {
  value = aws_dynamodb_table.terraform_lock.name
}

output "dev_tfvars_snippet" {
  description = "Pegar en infrastructure/terraform/dev.tfvars"
  value       = <<-EOT
    terraform_state_bucket     = "${aws_s3_bucket.terraform_state.id}"
    terraform_state_lock_table = "${aws_dynamodb_table.terraform_lock.name}"
    terraform_state_key        = "prode/terraform.tfstate"
  EOT
}
