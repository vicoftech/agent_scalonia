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
- Bot de Telegram **Scalonia** ya provisionado: el token vive en Secrets Manager como **`SCALONIA_TELEGRAM_BOT_TOKEN`** (no crear un secreto `TELEGRAM_BOT_TOKEN` nuevo).

---

## 3. Token de Telegram (`SCALONIA_TELEGRAM_BOT_TOKEN`)

Este proyecto reutiliza el **mismo bot** que la aplicación Scalonia. La Lambda del webhook lee el secreto por id lógico **`SCALONIA_TELEGRAM_BOT_TOKEN`** (ver `infrastructure/lambdas/telegram_webhook/handler.py` y la env `TELEGRAM_SECRET_ID` en Terraform).

**Si el secreto ya existe** (caso habitual), solo necesitás el ARN para `dev.tfvars` (paso 5):

```bash
aws secretsmanager describe-secret \
  --secret-id SCALONIA_TELEGRAM_BOT_TOKEN \
  --profile asap_dev \
  --region us-east-1 \
  --query ARN \
  --output text
```

**Si aún no está en Secrets Manager** (solo en el primer despliegue de Scalonia), crealo una vez con el token del bot existente:

```bash
aws secretsmanager create-secret \
  --name SCALONIA_TELEGRAM_BOT_TOKEN \
  --secret-string "BOT_TOKEN" \
  --profile asap_dev \
  --region us-east-1
```

Para rotar o actualizar el valor:

```bash
aws secretsmanager put-secret-value \
  --secret-id SCALONIA_TELEGRAM_BOT_TOKEN \
  --secret-string "BOT_TOKEN" \
  --profile asap_dev \
  --region us-east-1
```

En la política IAM de la Lambda, Terraform usa el **ARN** del secreto (`variable telegram_secret_arn`) en `GetSecretValue`.

> **Webhook único:** Telegram permite **una** URL de webhook por bot. Si la app Scalonia ya registró `setWebhook` a otra URL, al apuntar este MVP a `telegram_webhook_url` la otra dejará de recibir updates hasta que vuelvas a configurar su webhook (o uses otro bot solo para Prode).

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

### 5.1 Variables (`dev.tfvars`)

Terraform **no carga solo** `dev.tfvars`: hay que pasarlo con `-var-file=dev.tfvars` en cada `plan` / `apply` (o copiar el archivo a `terraform.tfvars`, que sí se carga automático).

```bash
cd infrastructure/terraform
cp dev.tfvars.example dev.tfvars
```

Editá `dev.tfvars` con valores reales:

| Variable | Ejemplo / notas |
|----------|-----------------|
| `env` | `"dev"` → tabla DynamoDB `ProdeTable-dev` |
| `aws_region` | `"us-east-1"` (tiene default en Terraform; conviene fijarlo igual) |
| `aws_profile` | `"asap_dev"` — **obligatorio en local**; el provider AWS lo usa para credenciales (sin esto suele fallar por permisos) |
| `aurora_cluster_identifier` | `"aurora-pg-asap-dev"` (solo data source / outputs; **no crea** el cluster). `""` si no querés outputs Aurora |
| `telegram_secret_arn` | ARN del paso 3 (`SCALONIA_TELEGRAM_BOT_TOKEN`) |
| `terraform_state_bucket` | Bucket S3 del state (output `state_bucket_name` del bootstrap) |
| `terraform_state_lock_table` | Tabla DynamoDB lock (`prode-terraform-state-lock`) |
| `terraform_state_key` | `"prode/terraform.tfstate"` (default; no suele cambiar) |

Ejemplo completo en `infrastructure/terraform/dev.tfvars.example`.

### 5.2 Backend remoto (S3 + DynamoDB lock) — obligatorio antes del primer apply

El state de Terraform **no puede** quedar solo en tu disco: hace falta un **bucket S3** y una **tabla DynamoDB** para el lock. Eso **no** lo crea el stack principal: lo crea el **bootstrap** (una vez por cuenta AWS).

#### Paso A — Bootstrap (crear bucket + tabla lock)

```bash
cd infrastructure/terraform
cp dev.tfvars.example dev.tfvars   # si aún no existe
export AWS_PROFILE=asap_dev

./bin/bootstrap.sh
# equivalente: make bootstrap
```

Crea:

| Recurso | Nombre |
|---------|--------|
| Bucket S3 | `prode-terraform-state-<ACCOUNT_ID>` |
| Tabla DynamoDB lock | `prode-terraform-state-lock` |

El bootstrap usa estado **local** en `bootstrap/` (normal: el bucket aún no existe).

#### Paso B — Init del stack principal (usa ese bucket)

```bash
# mismo directorio: infrastructure/terraform
./bin/init-backend.sh
# equivalente: make init
```

El script lee `aws_profile` de `dev.tfvars`, completa `terraform_state_bucket` con tu cuenta AWS, verifica que existan bucket y tabla, genera `backend/dev.hcl` y corre `terraform init` sin prompts.

Si saltás el bootstrap, `init-backend.sh` falla con un mensaje indicando que corras `./bin/bootstrap.sh` primero.

**No uses** `terraform init` a secas: el backend S3 está vacío en código y Terraform pedirá `bucket` por teclado. Siempre `./bin/init-backend.sh` o:

```bash
terraform init -input=false -reconfigure -backend-config=backend/dev.hcl
```

Opcional (para que `terraform init` tome el backend sin flags): `source env.sh` y luego `./bin/init-backend.sh` una vez para generar `backend/dev.hcl`.

Si ya habías corrido `plan` con **estado local** y querés subirlo a S3:

```bash
./bin/init-backend.sh -migrate-state
```

Elegí workspace `dev` (el estado remoto queda bajo `env:/dev/...`):

```bash
terraform workspace select dev || terraform workspace new dev
```

| Recurso | Nombre por defecto |
|---------|-------------------|
| Bucket S3 | `prode-terraform-state-<ACCOUNT_ID>` |
| Tabla lock DynamoDB | `prode-terraform-state-lock` |
| Key del state | `prode/terraform.tfstate` (prefijo workspace: `env:/dev/...`) |

Detalle: `infrastructure/terraform/bootstrap/README.md`.

### 5.3 Perfil AWS

El provider usa **`aws_profile`** en `dev.tfvars` (`asap_dev`). El backend S3 usa la misma cadena de credenciales si exportás:

```bash
export AWS_PROFILE=asap_dev
aws sts get-caller-identity --profile asap_dev
```

### 5.4 Plan y apply (sin prompts interactivos)

El stack incluye **AgentCore Runtime** (`agent_runtime.tf`): empaqueta `agent/` + dependencias, sube a S3 y crea runtime + endpoint `LIVE`. No hace falta `agentcore deploy`.

```bash
cd infrastructure/terraform
make prepare   # construye ZIPs del agente y de la Lambda webhook (primera vez o tras cambios en código)
make plan      # init backend + plan
make apply     # apply con -auto-approve
```

Equivalente manual:

```bash
./bin/build-agent-zip.sh ../.. .build/agent-runtime.zip
./bin/build-telegram-lambda.sh ../lambdas/telegram_webhook .build/telegram_webhook.zip
./bin/init-backend.sh
terraform workspace select dev || terraform workspace new dev
terraform apply -var-file=dev.tfvars -input=false -auto-approve
```

Cada `plan` / `apply` requiere haber corrido `./bin/init-backend.sh` (o `make init`) y **`make prepare`** si cambiaste `agent/` o el handler.

**Alternativa:** si preferís no usar `-var-file` en cada comando:

```bash
cp dev.tfvars terraform.tfvars   # también está en .gitignore
terraform plan  -input=false
terraform apply -input=false
```

### 5.5 Outputs

```bash
terraform output -raw telegram_webhook_url
terraform output dynamodb_table_name
```

Configurá **`agentcore.json`** (o variables del deploy) para que **`DYNAMODB_TABLE`** coincida con el output (ej. `ProdeTable-dev`). La Lambda ya recibe el nombre desde Terraform.

---

## 6. AgentCore (agente) — incluido en Terraform

El runtime del agente se crea en el mismo `terraform apply` (recurso `aws_bedrockagentcore_agent_runtime` + endpoint `LIVE`).

Outputs útiles:

```bash
terraform output agent_runtime_endpoint_arn
terraform output agent_runtime_id
```

**Desarrollo local** (opcional, sin Terraform):

```bash
pip install bedrock-agentcore-starter-toolkit
agentcore configure --entrypoint agent/main.py --name prode-mundial-2026
agentcore launch --local
```

---

## 7. Webhook de Telegram

La URL debe ser exactamente la del API HTTP (incluye stage `$default`):

```text
https://xxxx.execute-api.us-east-1.amazonaws.com/webhook/telegram
```

Obtené la URL (desde `infrastructure/terraform`):

```bash
terraform output -raw telegram_webhook_url
```

Registrá el webhook:

```bash
# Sustituí <BOT_TOKEN> por el valor del secreto SCALONIA_TELEGRAM_BOT_TOKEN (solo en tu máquina, no en el repo)
curl -X POST "https://api.telegram.org/bot<BOT_TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d "{\"url\": \"<telegram_webhook_url>\"}"
```

Verificá:

```bash
curl "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo"
```

El token es el mismo que usa Scalonia; no generes un bot nuevo salvo que quieras separar webhooks.

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
| 1 | Confirmar secreto `SCALONIA_TELEGRAM_BOT_TOKEN` en SM y copiar ARN a `telegram_secret_arn` |
| 2 | Crear secreto DB (`AURORA_SYNC_SECRET_ARN`) + definir `RDS_PROXY_ENDPOINT` |
| 3 | `poetry run alembic upgrade head` (o DDL manual único con `aurora_schema.sql`) |
| 4a | `./bin/bootstrap.sh` — crea bucket S3 + tabla lock DynamoDB |
| 4b | `./bin/init-backend.sh` — init remoto (requiere 4a) |
| 4c | `terraform apply -var-file=dev.tfvars` — stack principal |
| 5 | `make apply` (incluye AgentCore Runtime + endpoint LIVE) |
| 6 | Alinear `DYNAMODB_TABLE` en `agentcore.json` con `terraform output dynamodb_table_name` (solo para CLI local) |
| 7 | `setWebhook` con `terraform output -raw telegram_webhook_url` |
| 8 | (Cuando exista) enganchar DynamoDB stream → Lambda sync |

---

## 10. Referencias en el repo

| Archivo | Rol |
|---------|-----|
| `infrastructure/db/aurora_schema.sql` | DDL de referencia (y ejecución manual opcional) |
| `migrations/versions/0001_initial_schema.py` | Schema aplicado por **Alembic** (recomendado) |
| `infrastructure/terraform/` | Data layer + webhook HTTP |
| `infrastructure/terraform/dev.tfvars.example` | Plantilla de variables para `plan` / `apply` en dev |
| `infrastructure/terraform/bootstrap/` | Crea bucket S3 + tabla lock DynamoDB para el state |
| `infrastructure/terraform/bin/init-backend.sh` | `terraform init` leyendo `terraform_state_*` de `dev.tfvars` |
| `agentcore.json` | Entrypoint y variables del agente |

Si querés, el siguiente paso es ampliar Terraform para incluir la Lambda `sync` + event stream mapping en el mismo checklist.
