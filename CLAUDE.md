# Prode Mundial 2026 — Bedrock AgentCore + Strands + Aurora + DynamoDB

## Stack
- **Agent runtime**: Bedrock AgentCore Runtime (ARM64, serverless, microVM por sesión)
- **Framework**: Strands Agents SDK — `@tool`, `Agent`, `stream_async`
- **Modelo**: `us.anthropic.claude-sonnet-4-20250514` vía Amazon Bedrock
- **DB operativa**: DynamoDB On-Demand, Single-Table, 4 GSIs — escrituras + lookups sub-5ms
- **DB relacional**: Aurora PostgreSQL 16 Serverless v2 + RDS Proxy — JOINs + reporting
- **Sync**: DynamoDB Streams → Lambda `sync_dynamo_to_aurora` → Aurora (upsert idempotente)
- **ORM**: SQLAlchemy 2.x + asyncpg | Migrations: Alembic (solo CI/CD)
- **Lenguaje**: Python 3.12, snake_case/PascalCase

## Patrón de streaming OBLIGATORIO
```python
app = BedrockAgentCoreApp()
agent = Agent(model="us.anthropic.claude-sonnet-4-20250514", tools=[...])

@app.entrypoint
async def agent_invocation(payload: dict):
    stream = agent.stream_async(payload["prompt"])
    async for event in stream:
        yield event

if __name__ == "__main__": app.run()
```

## Arquitectura híbrida — cuándo usar cada store

| Operación | Store |
|-----------|-------|
| Verificar veda activa | DynamoDB GetItem |
| Escribir predicción | DynamoDB PutItem + condition_expression |
| Lookup usuario por platform_id | DynamoDB GSI-1-platform |
| Sesión trivia activa | DynamoDB (TTL 30min) |
| Ranking de grupo con alias | Aurora → v_group_ranking |
| Historial predicciones | Aurora → v_user_prediction_history |
| Desglose de puntos | Aurora → v_user_score_summary |
| Usuarios sin predicción | Aurora → v_members_without_prediction |

**Aurora es SOLO LECTURA desde el agente. La Lambda sync es el único writer.**

## Estado MVP — Sprint 0

- [x] `agent/main.py` — agente base con streaming
- [x] `agent/tools/echo_tool.py` — smoke test
- [x] `infrastructure/lambdas/telegram_webhook/handler.py` — webhook funcional
- [x] `infrastructure/db/aurora_schema.sql` — DDL completo + 4 vistas
- [x] `infrastructure/terraform/` — DynamoDB + Cognito + HTTP API (`/webhook/telegram`) + Lambda; data source Aurora opcional
- [x] `infrastructure/lambdas/sync_dynamo_to_aurora/handler.py` — puente
- [x] `migrations/versions/0001_initial_schema.py` — Alembic migration

## Scoring (SPEC-2026-013)
```
Exacto            → 5 pts
Ganador+diferencia → 3 pts
Solo ganador       → 1 pt
Incorrecto         → 0 pts
Trivia easy/medium/hard → +1/+2/+3 pts
Fases eliminatorias: scoring sobre result_90min (ignorar ET/penales)
```

## NUNCA
- NO hardcodear tokens → Secrets Manager
- NO loggear platform_id → SHA-256
- NO escribir predicción sin verificar veda_active en DynamoDB
- NO re-procesar scoring si result_processed=true
- NO escribir en Aurora desde @tools o el agente
- NO conectar Aurora sin RDS Proxy en Lambda
- NO Alembic en Lambda runtime
- NO Lambda directa para el agente — siempre agentcore deploy
