#!/usr/bin/env bash
# Verifica que el principal actual puede leer el AgentCore Runtime en Terraform state.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TFVARS="${TFVARS:-dev.tfvars}"
REGION="${AWS_REGION:-us-east-1}"

ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "AWS account: ${ACCOUNT}"

RUNTIME_ID="${1:-}"
if [[ -z "$RUNTIME_ID" ]]; then
  RUNTIME_ID=$(terraform state show -no-color 'aws_bedrockagentcore_agent_runtime.prode' 2>/dev/null \
    | awk '/agent_runtime_id/ {print $3}' | tr -d '"' | head -1 || true)
fi
if [[ -z "$RUNTIME_ID" ]]; then
  echo "Sin agent_runtime_id en state; omitiendo check."
  exit 0
fi

echo "Checking GetAgentRuntime: ${RUNTIME_ID}"
if aws bedrock-agentcore-control get-agent-runtime \
  --agent-runtime-id "$RUNTIME_ID" \
  --region "$REGION" >/dev/null; then
  echo "OK — principal puede leer el runtime."
  exit 0
fi

echo "ERROR: Forbidden al leer ${RUNTIME_ID}." >&2
echo "Usá credenciales de la cuenta del runtime (dev: asap_dev → 615216531593)." >&2
echo "En CI: secret AWS_ROLE_ARN_DEV = arn:aws:iam::615216531593:role/prode-github-actions-dev" >&2
exit 1
