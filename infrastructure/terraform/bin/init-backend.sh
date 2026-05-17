#!/usr/bin/env bash
# Genera backend/dev.hcl desde dev.tfvars y ejecuta terraform init (sin prompts).
# Requiere bootstrap previo (bucket S3 + tabla DynamoDB lock).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TFVARS="${TFVARS:-dev.tfvars}"
BACKEND_HCL="${BACKEND_HCL:-backend/dev.hcl}"

if [[ ! -f "$TFVARS" ]]; then
  echo "No existe $TFVARS — cp dev.tfvars.example dev.tfvars" >&2
  exit 1
fi

get_var() {
  local key="$1"
  local line val
  line=$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$TFVARS" | head -1) || true
  [[ -z "$line" ]] && return
  val=$(echo "$line" | sed -E 's/^[^=]+=[[:space:]]*//; s/^"//; s/"[[:space:]]*$//; s/[[:space:]]*$//')
  echo "$val"
}

set_var_in_tfvars() {
  local key="$1" value="$2"
  local tmp
  tmp=$(mktemp)
  if grep -qE "^[[:space:]]*${key}[[:space:]]*=" "$TFVARS"; then
    sed -E "s|^[[:space:]]*${key}[[:space:]]*=.*|${key} = \"${value}\"|" "$TFVARS" >"$tmp"
  else
    cp "$TFVARS" "$tmp"
    echo "${key} = \"${value}\"" >>"$tmp"
  fi
  mv "$tmp" "$TFVARS"
}

PROFILE=$(get_var aws_profile)
if [[ -z "${GITHUB_ACTIONS:-}" ]]; then
  PROFILE="${PROFILE:-asap_dev}"
fi
REGION=$(get_var aws_region)
REGION="${REGION:-us-east-1}"

if ! command -v aws >/dev/null 2>&1; then
  echo "Se necesita AWS CLI en PATH." >&2
  exit 1
fi

aws_cli() {
  if [[ -n "${PROFILE}" ]]; then
    aws --profile "$PROFILE" "$@"
  else
    aws "$@"
  fi
}

ACCOUNT_ID=$(aws_cli sts get-caller-identity --query Account --output text)
echo "AWS profile=${PROFILE:-<env-keys>} account_id=${ACCOUNT_ID}"

BUCKET=$(get_var terraform_state_bucket)
LOCK=$(get_var terraform_state_lock_table)
KEY=$(get_var terraform_state_key)

LOCK="${LOCK:-prode-terraform-state-lock}"
KEY="${KEY:-prode/terraform.tfstate}"

if [[ -z "$BUCKET" || "$BUCKET" == *"ACCOUNT_ID"* ]]; then
  BUCKET="prode-terraform-state-${ACCOUNT_ID}"
  set_var_in_tfvars terraform_state_bucket "$BUCKET"
  echo "terraform_state_bucket → ${BUCKET} (guardado en ${TFVARS})"
fi

bucket_ok=false
if aws_cli s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  bucket_ok=true
fi

lock_ok=false
if aws_cli dynamodb describe-table --table-name "$LOCK" --region "$REGION" >/dev/null 2>&1; then
  lock_ok=true
fi

if [[ "$bucket_ok" != true || "$lock_ok" != true ]]; then
  echo "ERROR: falta el backend remoto (bucket y/o tabla lock)." >&2
  [[ "$bucket_ok" != true ]] && echo "  - Bucket inexistente: s3://${BUCKET}" >&2
  [[ "$lock_ok" != true ]] && echo "  - Tabla lock inexistente: ${LOCK}" >&2
  echo "" >&2
  echo "Corré bootstrap una vez (crea ambos recursos):" >&2
  echo "  ./bin/bootstrap.sh" >&2
  echo "  # o: cd bootstrap && terraform init && terraform apply" >&2
  exit 1
fi

mkdir -p "$(dirname "$BACKEND_HCL")"
cat > "$BACKEND_HCL" <<EOF
# Generado por bin/init-backend.sh (perfil ${PROFILE}, cuenta ${ACCOUNT_ID})
bucket         = "${BUCKET}"
key            = "${KEY}"
region         = "${REGION}"
dynamodb_table = "${LOCK}"
encrypt        = true
EOF

echo "Wrote ${BACKEND_HCL}"
echo "Backend: s3://${BUCKET}/${KEY} (lock: ${LOCK}, region: ${REGION})"

# shellcheck source=/dev/null
source "$(dirname "$0")/tf-env.sh"
terraform init -input=false -reconfigure -backend-config="${BACKEND_HCL}" "$@"
