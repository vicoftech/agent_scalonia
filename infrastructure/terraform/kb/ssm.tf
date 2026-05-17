resource "aws_ssm_parameter" "kb_s3_bucket" {
  name  = "/${var.project_name}/${var.env}/kb_s3_bucket"
  type  = "String"
  value = aws_s3_bucket.kb_documents.bucket
}
