# Uso: source env.sh   (desde infrastructure/terraform)
# Hace que "terraform init" use backend/dev.hcl sin prompts.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
export TF_CLI_ARGS_init="-input=false -backend-config=${ROOT}/backend/dev.hcl"
