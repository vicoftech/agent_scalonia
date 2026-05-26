# GitHub Secrets — entorno `development` (dev)

**No pegues la API key de Tavily en GitHub.** La key vive en **AWS Secrets Manager**; en tfvars solo va el **ARN**.

La API key ya fue cargada en:

`arn:aws:secretsmanager:us-east-1:615216531593:secret:prode-mundial/dev/tavily-api-key-N45thZ`

---

## 1. Secret `DEV_TFVARS` (recomendado)

En el repo: **Settings → Secrets and variables → Actions → Environment `development`**.

Nombre: **`DEV_TFVARS`**

Valor: copiá el bloque siguiente **tal cual** (sin `aws_profile`; CI usa OIDC):

```hcl
env                       = "dev"
aws_region                = "us-east-1"
aws_profile               = ""
aurora_cluster_identifier = "aurora-pg-asap-dev"

terraform_state_bucket     = "prode-terraform-state-615216531593"
terraform_state_lock_table = "prode-terraform-state-lock"
terraform_state_key        = "prode/terraform.tfstate"

telegram_secret_arn   = "arn:aws:secretsmanager:us-east-1:615216531593:secret:SCALONIA_TELEGRAM_BOT_TOKEN-JkUUHh"
telegram_bot_username = "scalonia_bot"
tavily_secret_arn     = "arn:aws:secretsmanager:us-east-1:615216531593:secret:prode-mundial/dev/tavily-api-key-N45thZ"

bedrock_model_id = "us.mistral.pixtral-large-2502-v1:0"

# SPEC-031 / SPEC-032 — colas resultado/scoring + collector + lifecycle (trivia/reminders/veda/scheduler).
# Si no están, el apply local no crea esas Lambdas (default Terraform = false).
# CI (GitHub Actions) las inyecta automáticamente en workspace dev cuando faltan; apply local debe declararlas.
enable_result_queues     = true
enable_result_collector  = true
enable_match_schedules   = true

# Obligatorio si ya desplegaste el módulo KB (sin esto CI destruye kb_ingest/kb_query):
rds_proxy_endpoint            = "aurora-pg-asap-dev.cluster-cgxq84qu0b72.us-east-1.rds.amazonaws.com"
db_name                       = "postgres"
aurora_sync_secret_arn        = "arn:aws:secretsmanager:us-east-1:615216531593:secret:prode-mundial/dev/aurora-sync-60iepS"
lambda_vpc_subnet_ids         = ["subnet-0778965dc1b21dfb7", "subnet-01ad385e56ce2a2b9"]
lambda_vpc_security_group_ids = ["sg-0773b50b361cb2068"]
kb_aurora_security_group_id   = "sg-0ff149c197120e05a"
kb_manage_aurora_lambda_vpc_ingress = false
```

Si el workflow falla con `kb_*_lambda_name` pasando de un nombre a `""`, el secret `DEV_TFVARS` no incluye el bloque KB de arriba.

---

## 2. Secrets sueltos (fallback si `DEV_TFVARS` vacío)

| Secret | Valor |
|--------|--------|
| `AWS_ROLE_ARN_DEV` | ARN del rol OIDC (salida `terraform output github_actions_role_arn` tras `enable_github_oidc`) |
| `TELEGRAM_SECRET_ARN_DEV` | `arn:aws:secretsmanager:us-east-1:615216531593:secret:SCALONIA_TELEGRAM_BOT_TOKEN-JkUUHh` |
| `TF_STATE_BUCKET_DEV` | `prode-terraform-state-615216531593` |
| `TF_STATE_LOCK_TABLE_DEV` | `prode-terraform-state-lock` |

---

## 3. Rotar la API key de Tavily

La key se compartió en chat. En [Tavily](https://app.tavily.com) generá una **nueva** key y actualizá el secreto:

```bash
aws secretsmanager put-secret-value \
  --secret-id prode-mundial/dev/tavily-api-key \
  --secret-string "NUEVA_API_KEY" \
  --profile asap_dev \
  --region us-east-1
```

El ARN (`...-N45thZ`) **no cambia** al rotar el valor.

---

## 4. Archivo local

`infrastructure/terraform/dev.tfvars` (gitignored) incluye `aws_profile = "asap_dev"` para apply local.
