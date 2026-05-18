# SPEC-2026-015 — Bedrock Guardrail + SSM + CloudWatch (módulo reutilizable)

resource "aws_bedrock_guardrail" "prode" {
  name        = "${var.project_name}-guardrail-${var.env}"
  description = "Guardrail Prode Mundial 2026 — solo fútbol y mundiales"

  blocked_input_messaging = join("\n", [
    "Soy el asistente del Prode Mundial 2026 ⚽",
    "Solo puedo ayudarte con temas de fútbol y mundiales.",
    "¿Tenés alguna pregunta sobre el Mundial 2026?",
  ])

  blocked_outputs_messaging = join("\n", [
    "Solo puedo responder sobre fútbol y mundiales.",
    "¿En qué puedo ayudarte sobre el Mundial 2026?",
  ])

  topic_policy_config {
    topics_config {
      name       = "politica-economia"
      definition = "Preguntas sobre política, economía, finanzas, inversiones o gobierno"
      examples   = ["¿Quién ganó las elecciones?", "¿Cómo está el dólar?"]
      type       = "DENY"
    }
    topics_config {
      name       = "salud-medicina"
      definition = "Consultas médicas, diagnósticos, tratamientos o medicamentos"
      examples   = ["¿Qué pastilla tomo para el dolor?"]
      type       = "DENY"
    }
    topics_config {
      name       = "otros-deportes"
      definition = "Deportes que no son fútbol: básquet, tenis, natación, atletismo, F1, rugby"
      examples   = ["¿Quién ganó el US Open?", "¿Cómo le fue a Verstappen?"]
      type       = "DENY"
    }
    topics_config {
      name       = "tecnologia-programacion"
      definition = "Software, hardware, programación, inteligencia artificial, startups"
      examples   = ["¿Cómo hago un loop en Python?", "¿Qué es un LLM?"]
      type       = "DENY"
    }
    # Sin topic "entretenimiento": bloqueaba falsos positivos ("mejor/peor final del mundial").
    # El system prompt acota el alcance a fútbol y mundiales.
  }

  content_policy_config {
    filters_config {
      type            = "HATE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "INSULTS"
      input_strength  = "MEDIUM"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "VIOLENCE"
      input_strength  = "MEDIUM"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "SEXUAL"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
  }

  tags = {
    Project     = var.project_name
    Environment = var.env
    ManagedBy   = "terraform"
  }
}

# Publicar versión usable en Converse (DRAFT no sirve en runtime)
resource "aws_bedrock_guardrail_version" "prode" {
  guardrail_arn = aws_bedrock_guardrail.prode.guardrail_arn
  description   = "Published ${var.env}"
}

resource "aws_ssm_parameter" "guardrail_id" {
  name  = "/${var.project_name}/${var.env}/guardrail_id"
  type  = "String"
  value = aws_bedrock_guardrail.prode.guardrail_id
}

resource "aws_ssm_parameter" "guardrail_version" {
  name  = "/${var.project_name}/${var.env}/guardrail_version"
  type  = "String"
  value = aws_bedrock_guardrail_version.prode.version
}

resource "aws_cloudwatch_metric_alarm" "guardrail_blocks" {
  alarm_name          = "${var.project_name}-guardrail-blocks-${var.env}"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "GuardrailInvocationCount"
  namespace           = "AWS/Bedrock"
  period              = 300
  statistic           = "Sum"
  threshold           = 20
  alarm_description   = "Más de 20 bloqueos de guardrail en 5 minutos"
  treat_missing_data  = "notBreaching"
  alarm_actions       = var.sns_alerts_arn != "" ? [var.sns_alerts_arn] : []

  dimensions = {
    GuardrailId = aws_bedrock_guardrail.prode.guardrail_id
  }
}
