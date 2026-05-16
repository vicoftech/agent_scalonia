# Terraform — Sprint 0+ (data + Telegram webhook)

- **DynamoDB** `ProdeTable-<env>`: módulo `terraform-aws-modules/dynamodb-table/aws` (~> 4.x).
- **Cognito** User Pool + app client.
- **HTTP API (v2)** `POST /webhook/telegram` → Lambda `prode-telegram-webhook-<env>`.
- **Aurora** (opcional): `var.aurora_cluster_identifier` solo lee un cluster existente (outputs de endpoint; no crea RDS ni RDS Proxy).

Variables obligatorias para apply: `env`, `telegram_secret_arn`, `agentcore_agent_id`. Opcional: `aurora_cluster_identifier` (ej. `aurora-pg-asap-dev` en cuenta dev).

## Uso local (perfil `asap_dev`, workspace `dev`)

```bash
cd infrastructure/terraform
export AWS_PROFILE=asap_dev   # PowerShell: $env:AWS_PROFILE="asap_dev"
cp terraform.tfvars.example terraform.tfvars
# Completar telegram_secret_arn, agentcore_agent_id, aurora_cluster_identifier en tfvars

terraform init
terraform workspace select dev  || terraform workspace new dev
terraform plan
terraform apply
```

Tras el apply: `terraform output telegram_webhook_url` → usar en `setWebhook` de Telegram. Tabla Dynamo: `ProdeTable-dev` si `env=dev` (alinear `agentcore.json` / env del agente).

## CI / deploy

Los workflows ejecutan `terraform init` + `apply` en el runner. **Sin backend remoto (S3 + DynamoDB lock), el estado no persiste entre ejecuciones** y el apply no es usable en producción. Ver `backend.tf.example` y configurá `terraform init` con `-backend-config=...` o un `backend.tf` local no versionado.

GitHub Actions usa las credenciales AWS del environment (`staging` / `production`).

## Outputs

Outputs útiles: `telegram_webhook_url`, `dynamodb_table_name`, `dynamodb_stream_arn`, `aurora_cluster_endpoint`, `cognito_user_pool_id`.
