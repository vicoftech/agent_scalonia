#!/usr/bin/env bash
# Crea bucket S3 + tabla DynamoDB para el state remoto (una vez por cuenta AWS).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BOOTSTRAP_DIR="${ROOT}/bootstrap"
TFVARS="${TFVARS:-${ROOT}/dev.tfvars}"

PROFILE="asap_dev"
if [[ -f "$TFVARS" ]]; then
  line=$(grep -E '^[[:space:]]*aws_profile[[:space:]]*=' "$TFVARS" | head -1) || true
  if [[ -n "$line" ]]; then
    PROFILE=$(echo "$line" | sed -E 's/^[^=]+=[[:space:]]*//; s/^"//; s/"[[:space:]]*$//')
  fi
fi

export AWS_PROFILE="$PROFILE"
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

echo "Bootstrap (profile=${AWS_PROFILE}, region=${AWS_DEFAULT_REGION})"
cd "$BOOTSTRAP_DIR"
terraform init -input=false
terraform plan -input=false -out=tfplan
terraform apply -input=false -auto-approve tfplan
rm -f tfplan

echo ""
echo "Listo. Siguiente paso desde infrastructure/terraform:"
echo "  ./bin/init-backend.sh"
