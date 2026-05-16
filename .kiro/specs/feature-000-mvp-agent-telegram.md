# Spec: FEATURE-000 — MVP: Agente base + streaming Telegram

epic: EPIC-2026-001
sprint: Sprint-0
modo_ejecucion: IA-Assisted + Humano (deploy y smoke test)

## Objective
Pipeline E2E mínimo: agente Strands en AgentCore Runtime con streaming,
conectado a Telegram. Sin features de negocio. Solo validar el stack.

## Requirements

- requirement_id: US-000
  title: Pipeline E2E funciona
  acceptance_criteria:
    - 'agentcore deploy exitoso → user envía cualquier mensaje → respuesta en < 5s'
    - 'Patrón @app.entrypoint async + stream_async + yield obligatorio'
    - 'Lambda webhook invoca vía boto3.invoke_agent() + consume EventStream'

- requirement_id: US-001
  title: Streaming acumula correctamente
  acceptance_criteria:
    - 'Todos los chunks["bytes"] del EventStream se decodifican y acumulan'
    - 'Mensaje final enviado a Telegram completo, sin truncar'
    - 'Mensajes > 4096 chars se parten en múltiples sendMessage'

- requirement_id: US-002
  title: echo_tool smoke test
  acceptance_criteria:
    - 'echo_tool retorna: echo, timestamp UTC, status="MVP operativo", features_pending'

## Tasks

- task_id: TASK-000-001
  title: agent/main.py — entrypoint + stream_async
  agent_mode: assisted
  estimate_hours: 3

- task_id: TASK-000-002
  title: agent/tools/echo_tool.py
  agent_mode: auto
  estimate_hours: 1

- task_id: TASK-000-003
  title: telegram_webhook/handler.py — invoke_agent + EventStream consumer
  agent_mode: assisted
  estimate_hours: 4

- task_id: TASK-000-004
  title: Terraform DataStack — DynamoDB + Cognito
  agent_mode: auto
  estimate_hours: 3

- task_id: TASK-000-005
  title: Terraform AuroraStack — Serverless v2 + RDS Proxy
  agent_mode: manual
  estimate_hours: 4

- task_id: TASK-000-006
  title: Alembic env.py + 0001_initial_schema migration + GitHub Actions step
  agent_mode: assisted
  estimate_hours: 2

- task_id: TASK-000-007
  title: agentcore configure + deploy staging + smoke test E2E
  agent_mode: manual
  estimate_hours: 4

## Constraints
- Lambda webhook SIEMPRE retorna 200 a Telegram, incluso con errores internos
- platform_id hasheado con SHA-256 antes de cualquier log o almacenamiento
- session_id = "tg-" + sha256(chat_id)[:32] para continuidad de conversación
