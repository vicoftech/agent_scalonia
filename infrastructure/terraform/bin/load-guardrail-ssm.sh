#!/usr/bin/env bash
# Lee guardrail_id y guardrail_version desde SSM (SPEC-2026-015 TASK-015-003).
# Uso: eval "$(./bin/load-guardrail-ssm.sh dev)"   o   source tras export manual
set -euo pipefail

ENV="${1:-dev}"
PROJECT_NAME="${PROJECT_NAME:-prode-mundial}"
REGION="${AWS_REGION:-us-east-1}"

ID_PARAM="/${PROJECT_NAME}/${ENV}/guardrail_id"
VER_PARAM="/${PROJECT_NAME}/${ENV}/guardrail_version"

GUARDRAIL_ID="$(aws ssm get-parameter \
  --name "$ID_PARAM" \
  --region "$REGION" \
  --query 'Parameter.Value' \
  --output text)"

GUARDRAIL_VERSION="$(aws ssm get-parameter \
  --name "$VER_PARAM" \
  --region "$REGION" \
  --query 'Parameter.Value' \
  --output text)"

echo "export GUARDRAIL_ID=${GUARDRAIL_ID}"
echo "export GUARDRAIL_VERSION=${GUARDRAIL_VERSION}"
echo "# SSM: ${ID_PARAM} ${VER_PARAM}" >&2
