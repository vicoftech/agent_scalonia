# AIDLC Steering Context — Prode Mundial 2026 v2.0

## Proyecto
producto: Plataforma lúdica de predicciones del Mundial FIFA 2026
usuarios: Grupos de amigos y compañeros de trabajo
dominio: Entretenimiento / Gamificación / Deportes
temporalidad: Mundial FIFA 2026 — junio-julio 2026, 64 partidos

---

## Runtime del Agente
runtime: Amazon Bedrock AgentCore Runtime (serverless, ARM64, microVM por sesión)
framework: Strands Agents SDK (strands-agents + strands-agents-tools)
sdk_version: bedrock-agentcore>=1.6 + bedrock-agentcore-starter-toolkit>=0.3
patron_entrypoint: |
  app = BedrockAgentCoreApp()
  agent = Agent(model="us.anthropic.claude-sonnet-4-20250514", tools=[...])
  @app.entrypoint
  async def agent_invocation(payload):
      stream = agent.stream_async(payload["prompt"])
      async for event in stream:
          yield event
  if __name__ == "__main__": app.run()
modelo: us.anthropic.claude-sonnet-4-20250514
deploy_cli: agentcore deploy (NO Lambda directa para el agente)

---

## Stack Tecnológico Completo

| Capa | Servicio | Notas |
|------|----------|-------|
| Agent Runtime | Bedrock AgentCore Runtime | ARM64, serverless, microVM por sesión |
| Agent Framework | Strands Agents SDK | @tool, Agent, stream_async |
| LLM | claude-sonnet-4-20250514 | vía Bedrock, us-east-1 |
| DB operativa | Amazon DynamoDB On-Demand | Escrituras, estado real-time, lookups sub-5ms |
| DB relacional | Aurora PostgreSQL 16 Serverless v2 | JOINs, ranking, historial, reporting |
| DB sync | DynamoDB Streams → Lambda | Unidireccional Dynamo→Aurora, upsert idempotente |
| Connection pool | RDS Proxy | Obligatorio con Lambda, pool máx 10 conexiones |
| ORM | SQLAlchemy 2.x + asyncpg | Async nativo, compatible Lambda |
| Migrations | Alembic | Solo en CI/CD, NUNCA en Lambda runtime |
| Auth | Amazon Cognito User Pools | JWT 24h, custom: platform, platform_id, display_name |
| Knowledge Base | Amazon Bedrock Knowledge Base | S3 + OpenSearch Serverless, Titan Embeddings v2 |
| WebSocket | API Gateway WebSocket | Rankings real-time, TTL conexiones 8h |
| Webhooks entrada | API Gateway REST + Lambda | Python 3.12, normaliza → agente vía A2A |
| Scheduler | Amazon EventBridge Scheduler | Veda kickoff-30min, recordatorios, daily job 3:00 UTC |
| Mensajería | SQS + SNS | Notificaciones async, DLQ para sync fallida |
| Secretos | AWS Secrets Manager | Todos los tokens, credentials de DB |
| Config | SSM Parameter Store | Params no secretos |
| IaC | AWS CDK Python | Stacks separados por dominio |
| CI/CD | GitHub Actions | Alembic migrations antes del deploy |
| Lenguaje | Python 3.12 | snake_case funciones/vars, PascalCase clases |

---

## Arquitectura Híbrida de Datos — Principios INMUTABLES

### Principio 1: DynamoDB escribe, Aurora lee
- TODA escritura transaccional → DynamoDB (predecir, veda, trivia, scoring)
- TODA query con JOIN → Aurora (ranking con alias, historial, usuarios sin predicción)
- DynamoDB es la fuente de verdad. Aurora es siempre un espejo.

### Principio 2: Sincronización unidireccional y asíncrona
- DynamoDB Streams → Lambda `sync_dynamo_to_aurora` → Aurora upsert idempotente
- Aurora NUNCA escribe de vuelta a DynamoDB
- Lag de sincronización aceptable: < 2 segundos
- Si Aurora cae: escrituras siguen funcionando (solo afecta lecturas relacionales)

### Principio 3: DAOs estrictamente separados
- `src/dao/dynamo/` — escrituras + lookups directos
- `src/dao/aurora/` — queries con JOIN + reporting
- Las @tools eligen el DAO correcto según la operación

### Principio 4: RDS Proxy obligatorio
- Lambda + Aurora sin Proxy = agotamiento de conexiones
- Pool máximo 10 conexiones reales, multiplexadas entre todas las Lambdas

### Principio 5: Alembic en CI/CD, nunca en runtime
- `alembic upgrade head` corre en GitHub Actions antes del deploy
- Una Lambda `run_migrations` solo para emergencias manuales

---

## DynamoDB — Single-Table Design

Tabla: ProdeTable | Modo: On-Demand | Streams: NEW_AND_OLD_IMAGES | PITR: true | TTL: ttl_expiry

| Entidad | PK | SK | TTL |
|---------|----|----|-----|
| Perfil usuario | `USER#<uuid>` | `PROFILE` | — |
| Predicción | `USER#<uuid>` | `PRED#<match_uuid>` | — |
| Partido | `MATCH#<uuid>` | `DETAILS` | — |
| Resultado | `MATCH#<uuid>` | `RESULT` | — |
| Grupo | `GROUP#<uuid>` | `DETAILS` | — |
| Membresía | `GROUP#<uuid>` | `MEMBER#<user_uuid>` | — |
| Ranking global | `RANKING#GLOBAL` | `USER#<uuid>` | — |
| Ranking grupo | `RANKING#GROUP#<g_uuid>` | `USER#<uuid>` | — |
| Snapshot ranking | `RANKING_SNAP#<YYYY-MM-DD>` | `USER#<uuid>` | 90d |
| Trivia sesión | `USER#<uuid>` | `TRIVIA#<session_uuid>` | 30min |
| Trivia histórico | `USER#<uuid>` | `TRIVIA_HIST#<date>#<uuid>` | — |
| WS conexión | `WS#<connection_id>` | `DETAILS` | 8h |
| Job control | `JOB_CTRL#<job_name>` | `<YYYY-MM-DD>` | — |
| Cache search | `CACHE#<query_hash>` | `RESULT` | 24h |

GSIs:
- GSI-1-platform: platform (PK) | platform_id_hash (SK) — lookup usuario por webhook
- GSI-2-match-predictions: match_id (PK) | user_id (SK) — predicciones por partido
- GSI-3-group-members: group_id (PK) | user_id (SK) — miembros de grupo
- GSI-4-ranking-score: ranking_type (PK) | score (SK, Number) — ranking ordenado

---

## Aurora PostgreSQL — Tablas y vistas clave

Tablas: users, matches, match_results, predictions, groups, group_members, trivia_sessions, ranking_history

Vistas pre-armadas:
- v_group_ranking — ranking de grupo con alias y posición
- v_user_prediction_history — historial con datos del partido
- v_user_score_summary — desglose de puntos con posición global
- v_members_without_prediction — usuarios sin predicción (para recordatorio de veda)

---

## Reglas de Negocio Invariantes

### Puntuación
exacto: 5 pts | ganador+diferencia: 3 pts | ganador: 1 pt | incorrecto: 0 pts
fases_eliminatorias: scoring sobre result_90min (ignorar ET y penales)
trivia: easy=1, medium=2, hard=3 pts. Sin penalización. Máx 5 rondas/día.

### Operativas
veda: kickoff_utc - 30 minutos (EventBridge Scheduler, nombre determinístico: veda-{match_id})
predicciones: INMUTABLES post-veda (DynamoDB condition_expression)
max_grupo: 50 miembros
daily_job: cron(0 3 * * ? *) UTC — período 2026-06-11 a 2026-07-20

---

## Integraciones Externas
telegram: Webhook → Lambda → boto3.invoke_agent() → EventStream → sendMessage MarkdownV2
teams: Bot Framework → Lambda → boto3.invoke_agent() → Adaptive Card
web_search_tool: @tool Strands. Cache DynamoDB CACHE# TTL 24h. NO almacenar resultados > 24h.

---

## Restricciones Permanentes
- NUNCA hardcodear tokens/credentials → Secrets Manager
- NUNCA loggear platform_id → SHA-256 siempre
- NUNCA escribir predicciones sin verificar veda_active=true en DynamoDB
- NUNCA re-procesar scoring si result_processed=true (idempotencia)
- NUNCA escribir directamente en Aurora desde el agente o @tools
- NUNCA conectar a Aurora sin RDS Proxy en Lambda
- NUNCA correr Alembic en Lambda runtime
- El agente SIEMPRE en AgentCore Runtime — NO Lambda directa
