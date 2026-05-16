# ⚽ Agente ScalonIA Prode Mundial 2026

Plataforma de predicciones del Mundial FIFA 2026 para grupos de amigos y equipos de trabajo.
**Bedrock AgentCore Runtime + Strands Agents SDK + Aurora PostgreSQL + DynamoDB**

## Interfaces
| Canal | Tecnología |
|-------|-----------|
| Telegram | Bot API v7.x — MarkdownV2 |
| Microsoft Teams | Bot Framework — Adaptive Cards |

## Arquitectura de datos híbrida

```
DynamoDB On-Demand          Aurora PostgreSQL 16 Serverless v2
─────────────────           ─────────────────────────────────
Escrituras ✓                JOINs y reporting ✓
Lookups sub-5ms ✓           v_group_ranking ✓
Veda check atómico ✓        v_user_prediction_history ✓
Trivia sesión (TTL 30min)   v_user_score_summary ✓
WS conexiones (TTL 8h)      v_members_without_prediction ✓
Cache search (TTL 24h)
        ↓
DynamoDB Streams → Lambda sync_dynamo_to_aurora → Aurora (upsert idempotente)
```

## Quick Start

```bash
# 1. Instalar dependencias
poetry install

# 2. Configurar AgentCore
pip install bedrock-agentcore-starter-toolkit
agentcore configure --entrypoint agent/main.py --name prode-mundial-2026

# 3. Test local del agente
agentcore launch --local &
agentcore invoke --local --payload '{"prompt": "hola"}'

# 4. Deploy infra (Terraform): DynamoDB, Cognito, Lambda Telegram, HTTP API
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars   # completar ARN secreto Telegram + agent id
export AWS_PROFILE=asap_dev   # o el perfil de tu cuenta dev
terraform init
terraform workspace select dev || terraform workspace new dev   # opcional; default si un solo entorno
terraform apply
cd ../..

# 5. Alembic → Aurora (usa Secrets Manager + RDS Proxy / endpoint en env)
alembic upgrade head

# 6. Deploy agente
agentcore deploy --env dev   # o staging; alinear DYNAMODB_TABLE con ProdeTable-<env>

# 7. Webhook Telegram (sustituir TOKEN; la URL sale de: terraform -chdir=infrastructure/terraform output -raw telegram_webhook_url)
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{"url": "PASTE_WEBHOOK_URL_HERE"}'

# 8. Tests
poetry run pytest
```

## Scoring
| Predicción | Puntos |
|-----------|--------|
| Marcador exacto | **5 pts** |
| Ganador + diferencia de goles | **3 pts** |
| Solo ganador correcto | **1 pt** |
| Incorrecto | **0 pts** |
| Trivia easy/medium/hard | **+1/+2/+3 pts** |

Fases eliminatorias: scoring sobre resultado a 90 minutos.

## Sprints
| Sprint | Features | Estado |
|--------|---------|--------|
| Sprint 0 | MVP: Agente base + streaming + Aurora schema | 🔄 EN PROGRESO |
| Sprint 1 | Usuarios, Predicciones, Veda, Telegram | ⏳ |
| Sprint 2 | Resultados, Scoring, Rankings, Grupos, Teams | ⏳ |
| Sprint 3 | KB, Trivia, Daily Job, Hardening | ⏳ |

## Estructura
```
prode-mundial-2026/
├── agent/                          ← AgentCore Runtime (agentcore deploy)
│   ├── main.py                     ← @app.entrypoint + stream_async ✓
│   └── tools/                      ← @tool functions
├── src/
│   ├── scoring/scoring_engine.py   ← motor de puntos puro (Sprint 2)
│   ├── jobs/daily_ranking_job.py   ← job diario 3:00 UTC (Sprint 3)
│   ├── dao/dynamo/                 ← DynamoDB DAOs (escrituras)
│   └── dao/aurora/                 ← Aurora Repos (lecturas con JOIN)
├── infrastructure/
│   ├── db/
│   │   ├── aurora_schema.sql       ← DDL completo + 4 vistas ✓
│   │   └── DYNAMODB_SINGLE_TABLE.md ← modelo single-table + GSIs ✓
│   ├── terraform/                  ← IaC: DynamoDB, Cognito, API+Lambda Telegram ✓
│   ├── lambdas/
│   │   ├── telegram_webhook/       ← handler.py ✓
│   │   └── sync_dynamo_to_aurora/  ← handler.py ✓
├── migrations/
│   └── versions/0001_initial_schema.py  ← Alembic migration ✓
├── tests/
├── knowledge-base/
├── .aidlc/steering.md              ← fuente de verdad
├── .cursor/rules/                  ← adaptador Cursor (4 .mdc)
├── .kiro/specs/                    ← adaptador Kiro (4 specs)
├── CLAUDE.md                       ← adaptador Claude Code
├── agentcore.json
└── pyproject.toml
```
