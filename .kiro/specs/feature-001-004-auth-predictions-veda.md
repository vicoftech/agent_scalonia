# Spec: FEATURE-001 — Alta y Autenticación de Usuarios

sprint: Sprint-1 | modo: IA-Assisted

## Requirements

- requirement_id: US-003
  title: Registro exitoso vía Telegram (≤ 3 intercambios)
  acceptance_criteria:
    - 'SHA-256(chat_id) como platform_id_hash — NUNCA el chat_id en claro'
    - 'USER#<uuid>/PROFILE en DynamoDB → sync → users en Aurora'
    - 'Alta completada en ≤ 3 mensajes de ida y vuelta'

- requirement_id: US-004
  title: Usuario existente reconocido sin duplicado
  acceptance_criteria:
    - '/start → saludo con alias + posición ranking → SIN nuevo registro en DynamoDB'
    - 'Lookup usa GSI-1-platform'

## Tasks

- task_id: TASK-001
  title: src/dao/dynamo/user_dao.py — create, get_by_platform_hash, update_alias
  agent_mode: auto
  estimate_hours: 4

- task_id: TASK-002
  title: src/dao/aurora/user_repo.py — get_with_rank
  agent_mode: auto
  estimate_hours: 3

- task_id: TASK-003
  title: src/services/auth_service.py + Cognito post-confirmation trigger
  agent_mode: assisted
  estimate_hours: 4

---

# Spec: FEATURE-002 — Alta de Predicciones

sprint: Sprint-1 | modo: Humano (lógica crítica)

## Requirements

- requirement_id: US-005
  title: Predicción exitosa antes de veda
  acceptance_criteria:
    - 'check veda_active=false ANTES de cualquier escritura (DynamoDB GetItem)'
    - 'PutItem con ConditionExpression=attribute_not_exists (idempotente)'
    - 'Confirmación: "Predicción registrada: ARG 2 - 0 BRA ✅"'

- requirement_id: US-006
  title: Rechazo con veda activa — NUNCA escribe en DynamoDB
  acceptance_criteria:
    - 'veda_active=true → error VEDA_ACTIVE → "⛔ Veda activa" → SIN escritura'

## Tasks

- task_id: TASK-004
  title: src/dao/dynamo/prediction_dao.py — save (con veda check), update, get
  agent_mode: auto
  estimate_hours: 4

- task_id: TASK-005
  title: agent/tools/prediction_tool.py
  agent_mode: manual
  estimate_hours: 6

## Constraints
- SIEMPRE verificar veda_active en DynamoDB antes de escribir
- Predicciones INMUTABLES post-veda

---

# Spec: FEATURE-004 — Veda Pre-Partido (CRÍTICA)

sprint: Sprint-1 | modo: IA-Assisted

## Requirements

- requirement_id: US-012
  title: Veda automática 30min antes del kickoff
  acceptance_criteria:
    - 'EventBridge Scheduler: trigger_time = kickoff_utc - 30min'
    - 'Nombre del job: veda-{match_id} (determinístico = idempotente)'
    - 'Lambda veda_activator: UpdateItem con ConditionExpression="veda_active = :false"'

## Tasks

- task_id: TASK-006
  title: infrastructure/lambdas/veda_activator/handler.py
  agent_mode: assisted
  estimate_hours: 4

- task_id: TASK-007
  title: Terraform: EventBridge Scheduler + scheduler_manager Lambda
  agent_mode: assisted
  estimate_hours: 3
