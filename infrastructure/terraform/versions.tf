terraform {
  required_version = ">= 1.6.0"

  # Config completa en backend/dev.hcl (generado desde dev.tfvars).
  # No ejecutar "terraform init" solo: usar make init o ./bin/init-backend.sh
  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.17"
    }
    archive = {
      source  = "hashicorp/archive"
      version = ">= 2.4"
    }
    null = {
      source  = "hashicorp/null"
      version = ">= 3.2"
    }
    tls = {
      source  = "hashicorp/tls"
      version = ">= 4.0"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile != "" ? var.aws_profile : null

  default_tags {
    tags = {
      Project     = "prode-mundial-2026"
      Environment = var.env
      ManagedBy   = "terraform"
    }
  }
}
