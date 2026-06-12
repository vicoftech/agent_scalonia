#!/usr/bin/env bash
# Apply dev desde CI: prepare → init → workspace dev → apply → promote LIVE.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

TFVARS="${TFVARS:-dev.tfvars}"
WORKSPACE="${TF_WORKSPACE:-dev}"

if [[ -n "${DEV_TFVARS:-}" ]]; then
  printf '%s\n' "$DEV_TFVARS" >"$TFVARS"
elif [[ ! -f "$TFVARS" ]]; then
  echo "ERROR: falta ${TFVARS}. Configurá el secret DEV_TFVARS en GitHub (contenido de dev.tfvars)." >&2
  exit 1
fi

# CI usa credenciales del job, no ~/.aws profile.
if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
  if grep -qE '^[[:space:]]*aws_profile[[:space:]]*=' "$TFVARS"; then
    sed -i.bak -E 's/^[[:space:]]*aws_profile[[:space:]]*=.*/aws_profile = ""/' "$TFVARS"
  else
    echo 'aws_profile = ""' >>"$TFVARS"
  fi
  rm -f "${TFVARS}.bak"
fi

chmod +x bin/*.sh
make prepare
for _zip in .build/kb_ingest.zip .build/kb_query.zip .build/kb_enrichment_dispatcher.zip; do
  if [[ ! -f "$_zip" ]]; then
    echo "ERROR: falta ${_zip} — revisá Makefile prepare (build-kb-lambda)" >&2
    exit 1
  fi
done

export TFVARS
./bin/init-backend.sh -input=false
chmod +x bin/validate-kb-tfvars.sh
./bin/validate-kb-tfvars.sh

# TF_WORKSPACE (p. ej. en GitHub Actions) fija el workspace; no usar workspace select.
if [[ -n "${TF_WORKSPACE:-}" ]]; then
  echo "Terraform workspace: ${TF_WORKSPACE} (TF_WORKSPACE)"
elif terraform workspace list | grep -qE "^\s*\*?\s*${WORKSPACE}\s*$"; then
  terraform workspace select "$WORKSPACE"
else
  terraform workspace new "$WORKSPACE"
fi

# OIDC deploy role: aplicar política IAM antes del apply completo (Scheduler + AgentCore).
if grep -qE '^[[:space:]]*enable_github_oidc[[:space:]]*=[[:space:]]*true' "$TFVARS"; then
  echo "=== Pre-apply: IAM GitHub Actions deploy policy ==="
  terraform apply -var-file="$TFVARS" -input=false -auto-approve \
    -target=aws_iam_role_policy.github_actions_deploy[0]
  echo "Esperando propagación IAM (15s)..."
  sleep 15
fi

echo "=== Verify deploy principal (AgentCore) ==="
DEPLOY_ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
echo "Deploy account: ${DEPLOY_ACCOUNT}"
RUNTIME_ID=$(terraform state show -no-color 'aws_bedrockagentcore_agent_runtime.prode' 2>/dev/null \
  | awk '/agent_runtime_id/ {print $3}' | tr -d '"' | head -1 || true)
if [[ -n "$RUNTIME_ID" ]]; then
  if ! aws bedrock-agentcore-control get-agent-runtime \
    --agent-runtime-id "$RUNTIME_ID" \
    --region "${AWS_REGION:-us-east-1}" >/dev/null 2>&1; then
    echo "::error::Forbidden GetAgentRuntime (${RUNTIME_ID}). El rol OIDC debe ser prode-github-actions-dev en la misma cuenta que el runtime (615216531593)." >&2
    exit 1
  fi
  echo "AgentCore GetAgentRuntime OK (${RUNTIME_ID})"
fi

chmod +x bin/import-prode-brief-table-if-missing.sh
./bin/import-prode-brief-table-if-missing.sh

terraform apply -var-file="$TFVARS" -input=false -auto-approve

./bin/promote-agent-live.sh

terraform output -json | python3 -c "
import json, sys
o = json.load(sys.stdin)
print('agent_runtime_id:', o.get('agent_runtime_id', {}).get('value', '?'))
print('telegram_webhook_url:', o.get('telegram_webhook_url', {}).get('value', '?'))
"
