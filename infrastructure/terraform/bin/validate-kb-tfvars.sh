#!/usr/bin/env bash
# Evita apply en CI con tfvars incompletos que destruirían Lambdas KB ya en state.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TFVARS="${TFVARS:-dev.tfvars}"

if [[ ! -f "$TFVARS" ]]; then
  echo "validate-kb-tfvars: no existe ${TFVARS}" >&2
  exit 1
fi

kb_enabled_in_tfvars() {
  grep -qE '^[[:space:]]*rds_proxy_endpoint[[:space:]]*=[[:space:]]*"[^"]+"' "$TFVARS" || return 1
  grep -qE 'lambda_vpc_subnet_ids.*subnet-' "$TFVARS" || return 1
  if grep -qE '^[[:space:]]*aurora_sync_secret_arn[[:space:]]*=[[:space:]]*"arn:' "$TFVARS"; then
    return 0
  fi
  if grep -qE '^[[:space:]]*manage_aurora_secret[[:space:]]*=[[:space:]]*true' "$TFVARS"; then
    return 0
  fi
  return 1
}

if ! terraform state list 2>/dev/null | grep -q 'module\.kb\.aws_lambda_function\.kb_query'; then
  if ! kb_enabled_in_tfvars; then
    echo "validate-kb-tfvars: sin Lambdas KB en state y tfvars sin bloque KB (ok para deploy parcial)"
  fi
  exit 0
fi

if kb_enabled_in_tfvars; then
  echo "validate-kb-tfvars: OK — Lambdas KB en state y variables KB presentes en ${TFVARS}"
  exit 0
fi

cat >&2 <<EOF
::error::DEV_TFVARS incompleto: el state ya tiene Lambdas KB pero faltan variables en ${TFVARS}.

Terraform deshabilitaría kb_ingest/kb_query (outputs → "") y las destruiría en apply.

Agregá al secret DEV_TFVARS (GitHub → Environment development):

  rds_proxy_endpoint            = "aurora-pg-asap-dev.cluster-cgxq84qu0b72.us-east-1.rds.amazonaws.com"
  db_name                       = "postgres"
  aurora_sync_secret_arn        = "arn:aws:secretsmanager:us-east-1:615216531593:secret:prode-mundial/dev/aurora-sync-60iepS"
  lambda_vpc_subnet_ids         = ["subnet-0778965dc1b21dfb7", "subnet-01ad385e56ce2a2b9"]
  lambda_vpc_security_group_ids = ["sg-0773b50b361cb2068"]
  kb_aurora_security_group_id   = "sg-0ff149c197120e05a"
  kb_manage_aurora_lambda_vpc_ingress = false

Ver docs/github-secrets-dev.md
EOF
exit 1
