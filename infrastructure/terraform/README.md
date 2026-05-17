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

## CI

`make prepare` + `terraform apply` con secrets de state y `telegram_secret_arn`.
