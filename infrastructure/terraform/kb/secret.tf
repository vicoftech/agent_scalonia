# Credenciales DB para Lambdas KB (mismo cluster que rag-agents dev).

resource "aws_secretsmanager_secret" "aurora_sync" {
  count = var.manage_aurora_secret ? 1 : 0
  name  = "${var.project_name}/${var.env}/aurora-sync"
}

resource "aws_secretsmanager_secret_version" "aurora_sync" {
  count         = var.manage_aurora_secret ? 1 : 0
  secret_id     = aws_secretsmanager_secret.aurora_sync[0].id
  secret_string = jsonencode({
    username = var.aurora_db_username
    password = var.aurora_db_password
  })

  lifecycle {
    precondition {
      condition     = var.aurora_db_password != ""
      error_message = "aurora_db_password es obligatorio si manage_aurora_secret=true"
    }
  }
}
