# GitHub Actions → AWS sin access keys (OIDC / IAM role).
# Tras el primer apply: copiar output github_actions_role_arn al secret AWS_ROLE_ARN_DEV en GitHub.

locals {
  github_environment = var.github_actions_environment != "" ? var.github_actions_environment : (
    var.env == "dev" ? "development" : var.env == "staging" ? "staging" : var.env == "prod" ? "production" : var.env
  )
  github_oidc_sub      = "repo:${var.github_repository}:environment:${local.github_environment}"
  create_oidc_provider = var.enable_github_oidc && var.env == "dev"
}

data "tls_certificate" "github" {
  count = local.create_oidc_provider ? 1 : 0
  url   = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  count = local.create_oidc_provider ? 1 : 0
  url   = "https://token.actions.githubusercontent.com"

  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    replace(data.tls_certificate.github[0].certificates[0].sha1_fingerprint, ":", ""),
  ]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.enable_github_oidc && !local.create_oidc_provider ? 1 : 0
  url   = "https://token.actions.githubusercontent.com"
}

locals {
  github_oidc_provider_arn = var.enable_github_oidc ? (
    local.create_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
  ) : null
}

data "aws_iam_policy_document" "github_actions_assume" {
  count = var.enable_github_oidc ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.github_oidc_sub]
    }
  }
}

data "aws_iam_policy_document" "github_actions_deploy" {
  count = var.enable_github_oidc ? 1 : 0

  statement {
    sid    = "TerraformState"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      "arn:aws:s3:::${var.terraform_state_bucket}",
      "arn:aws:s3:::${var.terraform_state_bucket}/*",
    ]
  }

  statement {
    sid    = "TerraformLock"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:DeleteItem",
      "dynamodb:DescribeTable",
    ]
    resources = ["arn:aws:dynamodb:${var.aws_region}:${data.aws_caller_identity.current.account_id}:table/${var.terraform_state_lock_table}"]
  }

  statement {
    sid    = "DeployServices"
    effect = "Allow"
    actions = [
      "lambda:*",
      "apigateway:*",
      "dynamodb:*",
      "cognito-idp:*",
      "cognito-identity:*",
      "secretsmanager:*",
      "ssm:*",
      "s3:*",
      "logs:*",
      "events:*",
      "sns:*",
      "sqs:*",
      "ec2:*",
      "rds:*",
      "bedrock:*",
      "bedrock-agentcore:*",
      "bedrock-agentcore-control:*",
      "cloudwatch:*",
      "kms:Decrypt",
      "kms:Encrypt",
      "kms:GenerateDataKey",
      "kms:DescribeKey",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "IAMForStack"
    effect = "Allow"
    actions = [
      "iam:GetOpenIDConnectProvider",
      "iam:ListOpenIDConnectProviders",
      "iam:CreateOpenIDConnectProvider",
      "iam:DeleteOpenIDConnectProvider",
      "iam:UpdateOpenIDConnectProviderThumbprint",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:GetRole",
      "iam:UpdateRole",
      "iam:PassRole",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:GetRolePolicy",
      "iam:ListRolePolicies",
      "iam:ListAttachedRolePolicies",
      "iam:CreatePolicy",
      "iam:DeletePolicy",
      "iam:GetPolicy",
      "iam:CreatePolicyVersion",
      "iam:DeletePolicyVersion",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:TagPolicy",
      "iam:UntagPolicy",
      "iam:ListInstanceProfilesForRole",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "github_actions" {
  count              = var.enable_github_oidc ? 1 : 0
  name               = "prode-github-actions-${var.env}"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume[0].json
  description        = "GitHub Actions OIDC (${local.github_oidc_sub})"
}

resource "aws_iam_role_policy" "github_actions_deploy" {
  count  = var.enable_github_oidc ? 1 : 0
  name   = "deploy"
  role   = aws_iam_role.github_actions[0].id
  policy = data.aws_iam_policy_document.github_actions_deploy[0].json
}
