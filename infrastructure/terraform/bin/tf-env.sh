#!/usr/bin/env bash
# Source antes de terraform/aws: exporta perfil desde dev.tfvars y evita credenciales sueltas en el shell.
# Uso: . ./bin/tf-env.sh
set -euo pipefail

if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  _tf_env_bin="$(dirname "${BASH_SOURCE[0]}")"
elif [[ -n "${ZSH_VERSION:-}" ]]; then
  _tf_env_bin="$(dirname "${(%):-%x}")"
else
  _tf_env_bin="$(dirname "$0")"
fi
_ROOT="$(cd "${_tf_env_bin}/.." && pwd)"
TFVARS="${TFVARS:-${_ROOT}/dev.tfvars}"

_tf_get_var() {
  local key="$1"
  local line val
  line=$(grep -E "^[[:space:]]*${key}[[:space:]]*=" "$TFVARS" 2>/dev/null | head -1) || true
  [[ -z "$line" ]] && return
  val=$(echo "$line" | sed -E 's/^[^=]+=[[:space:]]*//; s/^"//; s/"[[:space:]]*$//; s/[[:space:]]*$//')
  echo "$val"
}

export AWS_PROFILE="$(_tf_get_var aws_profile)"
AWS_PROFILE="${AWS_PROFILE:-asap_dev}"
export AWS_DEFAULT_REGION="$(_tf_get_var aws_region)"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"

# Access keys en el entorno ganan al perfil; suelen ser el origen del user CICD equivocado.
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN

export AWS_PROFILE
export AWS_DEFAULT_REGION

if command -v aws >/dev/null 2>&1; then
  _acct=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || _acct="?"
  echo "AWS_PROFILE=${AWS_PROFILE} account=${_acct} region=${AWS_DEFAULT_REGION}"
fi
