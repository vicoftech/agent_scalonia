#!/usr/bin/env bash
# Adopta ProdeBriefTable-{env} si existe en AWS pero no está en el state (drift / recreate manual).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TFVARS="${TFVARS:-dev.tfvars}"

if [[ ! -f "$TFVARS" ]]; then
  echo "Skip import-prode-brief: no ${TFVARS}" >&2
  exit 0
fi

if ! grep -qE '^[[:space:]]*enable_daily_briefs[[:space:]]*=[[:space:]]*true' "$TFVARS"; then
  exit 0
fi

get_var() {
  local key="$1"
  local line val
  line=$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$TFVARS" | head -1) || true
  [[ -z "$line" ]] && return
  val=$(echo "$line" | sed -E 's/^[^=]+=[[:space:]]*//; s/^"//; s/"[[:space:]]*$//; s/[[:space:]]*$//')
  echo "$val"
}

ENV_NAME=$(get_var env)
ENV_NAME="${ENV_NAME:-dev}"
REGION=$(get_var aws_region)
REGION="${REGION:-${AWS_REGION:-us-east-1}}"
TABLE="ProdeBriefTable-${ENV_NAME}"
ADDR='aws_dynamodb_table.prode_brief[0]'

if terraform state show "$ADDR" >/dev/null 2>&1; then
  echo "ProdeBriefTable ya en state: ${TABLE}"
  exit 0
fi

if ! aws dynamodb describe-table --table-name "$TABLE" --region "$REGION" >/dev/null 2>&1; then
  echo "ProdeBriefTable no existe en AWS (${TABLE}); apply la creará."
  exit 0
fi

echo "=== Import ${TABLE} → ${ADDR} ==="
terraform import -var-file="$TFVARS" -input=false "$ADDR" "$TABLE"
