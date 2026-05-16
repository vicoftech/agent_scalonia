# Spec: INFRA — Stack de Infraestructura + Base de Datos Híbrida

sprint: Sprint-0 (prerrequisito) | modo: IA-Assisted con revisión Humana

## Objective
Provisionar DynamoDB (escrituras) + Aurora PostgreSQL Serverless v2 (lecturas con JOIN)
+ Lambda sync_dynamo_to_aurora (puente unidireccional) + AgentCore Runtime.

## Requirements

- requirement_id: INFRA-001
  title: DynamoDB ProdeTable con 4 GSIs y Streams
  acceptance_criteria:
    - 'On-Demand, PITR, TTL=ttl_expiry, Streams=NEW_AND_OLD_IMAGES'
    - '4 GSIs operativos con proyecciones calibradas'
    - 'Stream ARN disponible como output de Terraform (módulo DynamoDB) para Lambda sync'

- requirement_id: INFRA-002
  title: Aurora PostgreSQL 16 Serverless v2 + RDS Proxy
  acceptance_criteria:
    - 'min_acu=0.5 (warm standby), max_acu=4'
    - 'RDS Proxy con pool_size=10 — obligatorio para Lambda'
    - 'alembic upgrade head ejecutado por GitHub Actions antes del deploy'
    - 'Schema completo: 8 tablas, 4 vistas, triggers updated_at, roles prode_sync/prode_reader'

- requirement_id: INFRA-003
  title: Lambda sync_dynamo_to_aurora
  acceptance_criteria:
    - 'Trigger: DynamoDB Stream de ProdeTable'
    - 'Procesa: USER/PROFILE, MATCH/DETAILS, MATCH/RESULT, PRED#, GROUP/DETAILS, GROUP/MEMBER#, TRIVIA# (answered), RANKING_SNAP#'
    - 'Ignora: WS#, CACHE#, JOB_CTRL# (efímeros)'
    - 'Upsert ON CONFLICT DO UPDATE en todas las tablas'
    - 'SQS DLQ para mensajes fallidos'

- requirement_id: INFRA-004
  title: AgentCore Runtime deployado y accesible
  acceptance_criteria:
    - 'agentcore.json configurado: entrypoint=agent/main.py'
    - 'agentcore deploy exitoso → AGENTCORE_AGENT_ID en Parameter Store'
    - 'Lambda webhook puede invocar via boto3 bedrock-agent-runtime'

## Tasks

- task_id: TASK-INFRA-001
  title: Terraform BaseStack — IAM, Secrets Manager, CloudWatch
  agent_mode: assisted
  estimate_hours: 4

- task_id: TASK-INFRA-002
  title: Terraform DataStack — DynamoDB ProdeTable + 4 GSIs + Streams
  agent_mode: auto
  estimate_hours: 3

- task_id: TASK-INFRA-003
  title: Terraform DataStack — Cognito User Pool + triggers
  agent_mode: assisted
  estimate_hours: 3

- task_id: TASK-INFRA-004
  title: Terraform AuroraStack — Serverless v2 + RDS Proxy + security groups
  agent_mode: manual
  estimate_hours: 4

- task_id: TASK-INFRA-005
  title: migrations/env.py + alembic.ini + GitHub Actions step
  agent_mode: assisted
  estimate_hours: 2

- task_id: TASK-INFRA-006
  title: Terraform: Lambda sync_dynamo_to_aurora + DynamoDB Stream trigger + SQS DLQ
  agent_mode: assisted
  estimate_hours: 4

- task_id: TASK-INFRA-007
  title: Terraform: API Gateway REST (webhooks) + WebSocket
  agent_mode: assisted
  estimate_hours: 4

- task_id: TASK-INFRA-008
  title: Terraform: EventBridge Scheduler + SQS NotificationQueue
  agent_mode: assisted
  estimate_hours: 3

- task_id: TASK-INFRA-009
  title: Terraform: Bedrock Knowledge Base + S3 + OpenSearch Serverless
  agent_mode: manual
  estimate_hours: 5

- task_id: TASK-INFRA-010
  title: agentcore configure + agentcore deploy
  agent_mode: manual
  estimate_hours: 2

- task_id: TASK-INFRA-011
  title: GitHub Actions: ci.yml, deploy-staging.yml, deploy-prod.yml, kb-sync.yml
  agent_mode: assisted
  estimate_hours: 4

- task_id: TASK-INFRA-012
  title: CloudWatch Dashboards Ops + Business + Alarmas
  agent_mode: assisted
  estimate_hours: 3

## Aurora config
engine: aurora-postgresql 16.x
min_acu: 0.5 | max_acu: 4 | multi_az: false
rds_proxy: true (pool_size: 10)
region: us-east-1 (misma que DynamoDB)
costo estimado mundial (~2 meses): ~$10/mes total Aurora
