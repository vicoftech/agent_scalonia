#!/usr/bin/env bash
# Source antes de terraform/aws: exporta perfil desde dev.tfvars y evita credenciales sueltas en el shell.
# Uso: . ./bin/tf-env.sh
_sourced=false
if [[ -n "${BASH_VERSION:-}" ]]; then
  [[ "${BASH_SOURCE[0]:-}" != "${0:-}" ]] && _sourced=true
elif [[ -n "${ZSH_VERSION:-}" ]]; then
  # En zsh, source deja $0 como el shell (p. ej. zsh), no el path del script.
  case "${0:-}" in zsh|*-zsh|"") _sourced=true ;; esac
fi
if ! $_sourced; then
  set -euo pipefail
fi

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

export AWS_DEFAULT_REGION="$(_tf_get_var aws_region)"
AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-us-east-1}"
export AWS_DEFAULT_REGION

# CI (GitHub Actions): usar AWS_ACCESS_KEY_ID del job, sin perfil ~/.aws.
if [[ -n "${GITHUB_ACTIONS:-}" ]]; then
  unset AWS_PROFILE
else
  export AWS_PROFILE="$(_tf_get_var aws_profile)"
  AWS_PROFILE="${AWS_PROFILE:-asap_dev}"
  # En local, forzar perfil y no mezclar con keys sueltas en el shell.
  unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
  export AWS_PROFILE
fi

if command -v aws >/dev/null 2>&1; then
  _acct=$(aws sts get-caller-identity --query Account --output text 2>/dev/null) || _acct="?"
  echo "AWS_PROFILE=${AWS_PROFILE} account=${_acct} region=${AWS_DEFAULT_REGION}"
fi
