# Sprint 0 — Guía de despliegue (dev)

Pasos ordenados desde cero hasta tener **Telegram → API Gateway → Lambda → AgentCore** y **Aurora** con el schema listo para el espejo DynamoDB.

---

## 1. ¿Quién crea el esquema de Aurora?

| Componente | ¿Crea tablas/vistas en PostgreSQL? |
|------------|-------------------------------------|
| **Lambda `sync_dynamo_to_aurora`** | **No.** Asume que las tablas y vistas **ya existen**. Solo hace upserts (`ON CONFLICT DO UPDATE`, etc.) cuando hay eventos en el stream de DynamoDB. |
| **Alembic** (`alembic upgrade head`) | **Sí.** Es la forma prevista en el repo para crear el schema completo (equivalente al DDL). |
| **`infrastructure/db/aurora_schema.sql`** | **Referencia / opción manual.** Mismo modelo que la migración inicial; puedes ejecutarlo en `psql` si no usás Alembic en ese entorno (no recomendado si ya tenés CI con Alembic). |

**Conclusión:** tenés que aplicar el esquema **antes** de que la Lambda sync tenga sentido. Lo habitual es: **Secrets Manager (credenciales DB) + endpoint (Proxy o cluster) → `alembic upgrade head`**. La Lambda **no** reemplaza ese paso.

---

## 2. Prerrequisitos

- Cuenta AWS con permisos para DynamoDB, Cognito, Lambda, API Gateway v2, IAM, Secrets Manager, Bedrock (`InvokeAgent`).
- **Perfil** local (ej. `asap_dev`) y región **`us-east-1`** (o la que uses de forma consistente).
- **Python 3.12**, **Poetry**, **Terraform ≥ 1.6**, **AWS CLI v2**.
- **Cluster Aurora PostgreSQL** accesible (ej. `aurora-pg-asap-dev`). Ideal: **RDS Proxy** para el string de conexión que use Alembic/Lambdas según steering.
- Bot de Telegram y el **token** del bot (guardalo solo en Secrets Manager, nunca en el repo).

---

## 3. Token de Telegram en Secrets Manager

La Lambda del webhook lee el secreto por id **lógico** `TELEGRAM_BOT_TOKEN` (ver `infrastructure/lambdas/telegram_webhook/handler.py`). Lo más simple es crear el secreto con **ese nombre**.

Ejemplo (reemplazá `BOT_TOKEN` y el perfil/región):

```bash
aws secretsmanager create-secret \
  --name TELEGRAM_BOT_TOKEN \
  --secret-string "BOT_TOKEN" \
  --profile asap_dev \
  --region us-east-1
```

Si el secreto ya existe, actualizá el valor:

```bash
aws secretsmanager put-secret-value \
  --secret-id TELEGRAM_BOT_TOKEN \
  --secret-string "BOT_TOKEN" \
  --profile asap_dev \
  --region us-east-1
```

Obtené el **ARN** para Terraform (variable `telegram_secret_arn`):

```bash
aws secretsmanager describe-secret \
  --secret-id TELEGRAM_BOT_TOKEN \
  --profile asap_dev \
  --region us-east-1 \
  --query ARN \
  --output text
```

En la política IAM de la Lambda, Terraform usa ese ARN en `GetSecretValue`.

---

## 4. Secretos y variables para Alembic (Aurora)

`migrations/env.py` arma la URL con:

- `AURORA_SYNC_SECRET_ARN` — ARN del secreto en Secrets Manager con `username` y `password` (JSON) del usuario que usará el sync / migraciones.
- `RDS_PROXY_ENDPOINT` — hostname del **RDS Proxy** (recomendado) o, solo para pruebas puntuales, el endpoint del writer del cluster (**no** expongas esto en Lambdas sin Proxy en producción).

Ejemplo de cuerpo del secreto (JSON):

```json
{
  "username": "prode_sync",
  "password": "CAMBIAR"
}
```

En PowerShell, antes de `alembic upgrade head`:

```powershell
$env:AURORA_SYNC_SECRET_ARN = "arn:aws:secretsmanager:us-east-1:CUENTA:secret:..."
$env:RDS_PROXY_ENDPOINT    = "tu-proxy.proxy-xxxxx.us-east-1.rds.amazonaws.com"
$env:DB_NAME               = "prode"
$env:AWS_PROFILE           = "asap_dev"
$env:AWS_DEFAULT_REGION    = "us-east-1"
```

Desde la **raíz del repo**:

```bash
poetry install
poetry run alembic upgrade head
```

Esto aplica la revisión `0001_initial_schema` (tablas + vistas). Si algo falla por permisos o red, corregí SG/VPC/Proxy antes de seguir.

**Alternativa solo para diagnóstico:** conectarte con `psql` al cluster/Proxy y ejecutar el script `infrastructure/db/aurora_schema.sql` **una vez**. No hace falta hacer ambas cosas si Alembic ya corrió bien (evitás duplicar o divergir).

---

## 5. Terraform (DynamoDB, Cognito, Lambda Telegram, HTTP API)

```bash
cd infrastructure/terraform
cp terraform.tfvars.example terraform.tfvars
```

Editá `terraform.tfvars`, mínimo:

- `env` — ej. `dev` → tabla `ProdeTable-dev`.
- `aws_region` — ej. `us-east-1`.
- `aurora_cluster_identifier` — ej. `aurora-pg-asap-dev` (solo data source / outputs; **no crea** el cluster).
- `telegram_secret_arn` — ARN del paso 3.
- `agentcore_agent_id` — **después** del primer `agentcore deploy` (podés dejar un placeholder y volver a `apply` cuando tengas el ID real).

Perfil AWS:

```bash
export AWS_PROFILE=asap_dev
export AWS_DEFAULT_REGION=us-east-1
```

Workspace (estado separado por entorno):

```bash
terraform init
terraform workspace select dev || terraform workspace new dev
terraform plan
terraform apply
```

Salidas útiles:

```bash
terraform output telegram_webhook_url
terraform output dynamodb_table_name
```

Configurá **`agentcore.json`** (o variables del deploy) para que **`DYNAMODB_TABLE`** coincida con el nombre real (ej. `ProdeTable-dev`). La Lambda ya recibe el nombre desde Terraform.

> **Backend remoto:** para equipo/CI, configurá S3 + lock DynamoDB (ver `infrastructure/terraform/backend.tf.example`). En local podés usar estado local al principio.

---

## 6. AgentCore (agente)

En la raíz del repo:

```bash
pip install bedrock-agentcore-starter-toolkit
poetry install

agentcore configure --entrypoint agent/main.py --name prode-mundial-2026
agentcore deploy --env dev
```

Anotá el **agent id** y repetí `terraform apply` actualizando `agentcore_agent_id` en `terraform.tfvars` si hace falta.

---

## 7. Webhook de Telegram

La URL debe ser exactamente la del API HTTP (incluye stage `$default`):

```text
https://xxxx.execute-api.us-east-1.amazonaws.com/webhook/telegram
```

Obtené la URL con `terraform output -raw telegram_webhook_url` y registrá el webhook:

```bash
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"<telegram_webhook_url>\"}"
```

Verificá:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

---

## 8. Lambda `sync_dynamo_to_aurora` (fuera del Terraform actual)

El stream de DynamoDB y el trigger de esta Lambda **aún pueden no estar** en el `apply` actual. Cuando existan:

1. El esquema Aurora ya debe estar aplicado (**paso 4**).
2. Variables de entorno de la Lambda: credenciales/endpoint Aurora (vía Secrets/Proxy), nombre de tablas, etc., según `infrastructure/lambdas/sync_dynamo_to_aurora/handler.py`.

Hasta entonces, DynamoDB y Aurora pueden convivir sin sync automático; el MVP **Telegram → agente** no depende del sync.

---

## 9. Checklist rápido

| Paso | Acción |
|------|--------|
| 1 | Crear/actualizar secreto `TELEGRAM_BOT_TOKEN` y copiar ARN |
| 2 | Crear secreto DB (`AURORA_SYNC_SECRET_ARN`) + definir `RDS_PROXY_ENDPOINT` |
| 3 | `poetry run alembic upgrade head` (o DDL manual único con `aurora_schema.sql`) |
| 4 | `terraform workspace` + `terraform apply` con `tfvars` completo |
| 5 | `agentcore deploy` y alinear `agentcore_agent_id` + `DYNAMODB_TABLE` |
| 6 | `setWebhook` con `telegram_webhook_url` |
| 7 | (Cuando exista) enganchar DynamoDB stream → Lambda sync |

---

## 10. Referencias en el repo

| Archivo | Rol |
|---------|-----|
| `infrastructure/db/aurora_schema.sql` | DDL de referencia (y ejecución manual opcional) |
| `migrations/versions/0001_initial_schema.py` | Schema aplicado por **Alembic** (recomendado) |
| `infrastructure/terraform/` | Data layer + webhook HTTP |
| `agentcore.json` | Entrypoint y variables del agente |

Si querés, el siguiente paso es ampliar Terraform para incluir la Lambda `sync` + event stream mapping en el mismo checklist.
