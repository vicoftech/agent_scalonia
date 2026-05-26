# Terraform — Sprint 0+

Stack unificado: **DynamoDB, Cognito, AgentCore Runtime, Lambda Telegram, API GW**.

## Orden (dev, perfil `asap_dev`)

```bash
cd infrastructure/terraform
cp dev.tfvars.example dev.tfvars
export AWS_PROFILE=asap_dev

make bootstrap    # una vez: bucket state + lock DynamoDB
make apply        # prepare + init + apply (AgentCore incluido)
```

## Qué crea `terraform apply`

| Recurso | Descripción |
|---------|-------------|
| `aws_bedrockagentcore_agent_runtime` | Agente Strands (`agent/` + deps en S3) |
| `aws_bedrockagentcore_agent_runtime_endpoint` | Endpoint `LIVE` para invocar |
| `aws_lambda_function` | Webhook Telegram → `invoke_agent_runtime` |
| DynamoDB, Cognito, API GW | Data layer + auth + HTTP |

**No** hace falta `agentcore deploy` ni `agentcore_agent_id` en tfvars.

## Build de paquetes

Antes del primer `plan`/`apply`:

```bash
make prepare
```

Construye `.build/agent-runtime.zip` y `.build/telegram_webhook.zip`.

## Variables (`dev.tfvars`)

Ver `dev.tfvars.example`. Sin `agentcore_agent_id`.

## Outputs

```bash
terraform output agent_runtime_endpoint_arn
terraform output telegram_webhook_url
terraform output dynamodb_table_name
```

## CI (GitHub Actions)

| Workflow | Cuándo |
|----------|--------|
| `deploy-dev.yml` | Push a `dev`/`main` si cambia `agent/`, `infrastructure/lambdas/`, `src/`, `infrastructure/terraform/` |
| `kb-sync.yml` | Push si cambia `knowledge-base/` |
| `ci.yml` | Tests + `terraform validate` en cada push/PR |

Deploy: `make prepare` → `terraform apply` → `bin/promote-agent-live.sh` (endpoint LIVE = última versión del agente).

**Auth OIDC (recomendado, sin access keys):**

1. `make apply` en dev crea el rol `prode-github-actions-dev` y el proveedor OIDC.
2. Copiá el ARN: `terraform output github_actions_role_arn`
3. En GitHub → Settings → Environments → **development** → secret `AWS_ROLE_ARN_DEV` = ese ARN.
4. Repetí para staging/prod (`AWS_ROLE_ARN_STAGING`, `AWS_ROLE_ARN_PROD`) tras apply en cada workspace.

El trust policy solo permite asumir el rol desde `repo:vicoftech/agent_scalonia:environment:development` (etc.), no desde forks.

**Otros secrets:** `DEV_TFVARS` (contenido de `dev.tfvars`), `TELEGRAM_SECRET_ARN_DEV`, opcionalmente `TF_STATE_*` si no están en tfvars.

### SPEC-031 / SPEC-032 (resultados, colas, schedules por partido)

En `dev.tfvars` o en el secret `DEV_TFVARS`:

```hcl
enable_result_queues     = true
enable_result_collector  = true
enable_match_schedules   = true
```

Si no los definís, Terraform deja `false` y **no existen** Lambdas `prode-result-collector-dev`, `prode-trivia-pre-match-dev`, etc.

En **GitHub Actions** (`ci-terraform-apply.sh`), si el workspace es `dev` y el tfvars **no** incluye `enable_match_schedules`, el script `bin/ensure-dev-match-schedule-flags.sh` **añade** esas tres líneas antes del `terraform apply` para que el siguiente deploy cree el stack.

Para comprobar después del deploy:

```bash
AWS_PROFILE=… AWS_REGION=us-east-1 aws lambda list-functions \
  --query "Functions[?contains(FunctionName,'prode-result')].FunctionName" --output text
```
