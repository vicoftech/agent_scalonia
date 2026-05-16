variable "env" {
  type        = string
  description = "Deployment environment (e.g. staging, prod)."
}

variable "aws_region" {
  type        = string
  default     = "us-east-1"
  description = "AWS region for all resources in this stack."
}
