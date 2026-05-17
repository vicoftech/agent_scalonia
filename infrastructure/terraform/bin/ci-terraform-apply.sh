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

export TFVARS
./bin/init-backend.sh -input=false

terraform workspace select "$WORKSPACE" 2>/dev/null || terraform workspace new "$WORKSPACE"
terraform apply -var-file="$TFVARS" -input=false -auto-approve

./bin/promote-agent-live.sh

terraform output -json | python3 -c "
import json, sys
o = json.load(sys.stdin)
print('agent_runtime_id:', o.get('agent_runtime_id', {}).get('value', '?'))
print('telegram_webhook_url:', o.get('telegram_webhook_url', {}).get('value', '?'))
"
