#!/usr/bin/env bash
# Alinea el endpoint LIVE con la última versión del AgentCore Runtime (post-terraform apply).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f ./bin/tf-env.sh ]] && [[ -z "${GITHUB_ACTIONS:-}" ]]; then
  # shellcheck source=/dev/null
  source ./bin/tf-env.sh
fi

RUNTIME_ID="${AGENT_RUNTIME_ID:-}"
if [[ -z "$RUNTIME_ID" ]]; then
  RUNTIME_ID=$(terraform output -raw agent_runtime_id 2>/dev/null || true)
fi
if [[ -z "$RUNTIME_ID" ]]; then
  echo "promote-agent-live: sin agent_runtime_id (skip)" >&2
  exit 0
fi

aws_cli() {
  if [[ -n "${AWS_PROFILE:-}" ]]; then
    aws --profile "$AWS_PROFILE" "$@"
  else
    aws "$@"
  fi
}

VERSION=$(aws_cli bedrock-agentcore-control get-agent-runtime \
  --agent-runtime-id "$RUNTIME_ID" \
  --query agentRuntimeVersion --output text)

LIVE_VERSION=$(aws_cli bedrock-agentcore-control list-agent-runtime-endpoints \
  --agent-runtime-id "$RUNTIME_ID" \
  --query "runtimeEndpoints[?name=='LIVE'].liveVersion | [0]" --output text)

echo "AgentCore runtime=${RUNTIME_ID} latest=${VERSION} LIVE=${LIVE_VERSION}"

if [[ "$LIVE_VERSION" == "$VERSION" ]]; then
  echo "LIVE ya apunta a la versión ${VERSION}"
  exit 0
fi

aws_cli bedrock-agentcore-control update-agent-runtime-endpoint \
  --agent-runtime-id "$RUNTIME_ID" \
  --endpoint-name LIVE \
  --agent-runtime-version "$VERSION"

echo "LIVE actualizado → versión ${VERSION}"
