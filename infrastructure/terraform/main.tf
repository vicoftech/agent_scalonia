# DynamoDB ProdeTable — single-table + 4 GSIs + stream (módulo oficial terraform-aws-modules).
# Documentación de patrones PK/SK: ../db/dYNAMODB_SINGLE_TABLE.md

module "prode_table" {
  source  = "terraform-aws-modules/dynamodb-table/aws"
  version = "~> 4.0"

  name         = "ProdeTable-${var.env}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "partition_key"
  range_key    = "sort_key"

  attributes = [
    { name = "partition_key", type = "S" },
    { name = "sort_key", type = "S" },
    { name = "platform", type = "S" },
    { name = "platform_id_hash", type = "S" },
    { name = "match_id", type = "S" },
    { name = "user_id", type = "S" },
    { name = "group_id", type = "S" },
    { name = "ranking_type", type = "S" },
    { name = "score", type = "N" },
    { name = "created_by", type = "S" },
    { name = "created_at", type = "S" },
    { name = "invite_id", type = "S" },
    { name = "used_at", type = "S" },
  ]

  global_secondary_indexes = [
    {
      name            = "GSI-1-platform"
      hash_key        = "platform"
      range_key       = "platform_id_hash"
      projection_type = "INCLUDE"
      non_key_attributes = [
        "user_id",
        "alias",
        "notifications_enabled",
        "status",
        "is_admin",
      ]
    },
    {
      name               = "GSI-2-match-predictions"
      hash_key           = "match_id"
      range_key          = "user_id"
      projection_type    = "ALL"
    },
    {
      name            = "GSI-3-group-members"
      hash_key        = "group_id"
      range_key       = "user_id"
      projection_type = "INCLUDE"
      non_key_attributes = [
        "alias",
        "total_points",
        "joined_at",
      ]
    },
    {
      name            = "GSI-4-ranking-score"
      hash_key        = "ranking_type"
      range_key       = "score"
      projection_type = "INCLUDE"
      non_key_attributes = [
        "user_id",
        "alias",
        "match_points",
        "trivia_points",
      ]
    },
    {
      name            = "GSI-5-invites-by-creator"
      hash_key        = "created_by"
      range_key       = "created_at"
      projection_type = "ALL"
    },
    {
      name            = "GSI-6-invite-uses-by-invite"
      hash_key        = "invite_id"
      range_key       = "used_at"
      projection_type = "ALL"
    },
  ]

  server_side_encryption_enabled = true
  point_in_time_recovery_enabled = true
  ttl_enabled                    = true
  ttl_attribute_name             = "ttl_expiry"
  stream_enabled                 = true
  stream_view_type               = "NEW_AND_OLD_IMAGES"
  deletion_protection_enabled    = local.is_prod
  create_table                   = true
  autoscaling_enabled            = false
}

# Cognito — mismo contrato que el antiguo DataStack (CDK); atributos custom: `custom:platform`, etc.
# Atributos personalizados: platform, platform_id (hash SHA-256), display_name.

resource "aws_cognito_user_pool" "prode" {
  name = "ProdeUserPool-${var.env}"

  username_configuration {
    case_sensitive = false
  }

  admin_create_user_config {
    allow_admin_create_user_only = false
  }

  password_policy {
    minimum_length    = 8
    require_lowercase = false
    require_numbers   = false
    require_symbols   = false
    require_uppercase = false
  }

  schema {
    name                = "custom:platform"
    attribute_data_type = "String"
    mutable             = true
    required            = false
    string_attribute_constraints {}
  }
  schema {
    name                = "custom:platform_id"
    attribute_data_type = "String"
    mutable             = false
    required            = false
    string_attribute_constraints {}
  }
  schema {
    name                = "custom:display_name"
    attribute_data_type = "String"
    mutable             = true
    required            = false
    string_attribute_constraints {}
  }

  deletion_protection = local.is_prod ? "ACTIVE" : "INACTIVE"
  mfa_configuration   = "OFF"
}

resource "aws_cognito_user_pool_client" "prode_app" {
  name         = "ProdeAppClient"
  user_pool_id = aws_cognito_user_pool.prode.id

  generate_secret                      = false
  allowed_oauth_flows_user_pool_client = false

  explicit_auth_flows = [
    "ALLOW_USER_PASSWORD_AUTH",
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  access_token_validity  = 24
  id_token_validity      = 24
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}
