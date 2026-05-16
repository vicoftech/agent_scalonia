# ProdeTable — modelo single-table (4 GSIs)

Fuente de verdad de patrones PK/SK: `.cursor/rules/01-steering.mdc`.

**IaC:** `infrastructure/terraform/main.tf` (módulo [terraform-aws-modules/dynamodb-table](https://registry.terraform.io/modules/terraform-aws-modules/dynamodb-table/aws/latest)).

Regla de oro: DynamoDB escribe, Aurora lee. El stream `NEW_AND_OLD_IMAGES` alimenta la Lambda `sync_dynamo_to_aurora`.

## Claves y GSIs

| Entidad | PK | SK |
|--------|----|-----|
| Perfil usuario | `USER#<uuid>` | `PROFILE` |
| Predicción | `USER#<uuid>` | `PRED#<match_uuid>` |
| Partido | `MATCH#<uuid>` | `DETAILS` |
| Resultado | `MATCH#<uuid>` | `RESULT` |
| Grupo | `GROUP#<uuid>` | `DETAILS` |
| Membresía | `GROUP#<uuid>` | `MEMBER#<user_uuid>` |
| Ranking global | `RANKING#GLOBAL` | `USER#<uuid>` |
| Ranking grupo | `RANKING#GROUP#<g_uuid>` | `USER#<uuid>` |
| Snapshot ranking | `RANKING_SNAP#<date>` | `USER#<uuid>` |
| Trivia sesión | `USER#<uuid>` | `TRIVIA#<session_uuid>` |
| Trivia histórico | `USER#<uuid>` | `TRIVIA_HIST#<date>#<uuid>` |
| WS conexión | `WS#<connection_id>` | `DETAILS` |
| Job control | `JOB_CTRL#<job_name>` | `<YYYY-MM-DD>` |
| Cache web_search | `CACHE#<query_hash>` | `RESULT` |

| GSI | PK | SK |
|-----|----|-----|
| GSI-1-platform | `platform` | `platform_id_hash` |
| GSI-2-match-predictions | `match_id` | `user_id` |
| GSI-3-group-members | `group_id` | `user_id` |
| GSI-4-ranking-score | `ranking_type` | `score` (N) |

## TTL (`ttl_expiry`)

- WS conexiones: ~8 h  
- Trivia sesiones: ~30 min  
- Cache web_search: ~24 h  
- Ranking snapshots: ~90 d  
