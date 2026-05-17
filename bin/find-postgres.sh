#!/usr/bin/env bash
# Busca username postgres en [env].tfvars, outputs.tf y terraform output.
#
# Uso:
#   ./bin/find-postgres.sh
#   ./bin/find-postgres.sh --env dev
#   ./bin/find-postgres.sh --no-terraform-output
#
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
TF_DIR="${ROOT}/infrastructure/terraform"
ENV_FILTER=""
RUN_TF_OUTPUT=1

usage() {
  cat <<'EOF'
Uso: find-postgres.sh [opciones]

  --env ENV                  Solo dev.tfvars / dev.tfvars.example (ej. dev)
  --terraform-dir DIR        Directorio Terraform (default: infrastructure/terraform)
  --no-terraform-output      No ejecutar terraform output -json
  -h, --help                 Esta ayuda

No requiere argumentos posicionales; el repo root se detecta con git.
EOF
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage 0 ;;
    --env) ENV_FILTER="${2:?falta valor para --env}"; shift 2 ;;
    --terraform-dir) TF_DIR="${2:?falta valor para --terraform-dir}"; shift 2 ;;
    --no-terraform-output) RUN_TF_OUTPUT=0; shift ;;
    *)
      echo "Opción desconocida: $1" >&2
      echo "(¿Pusiste 'repo root' como argumentos? No hace falta.)" >&2
      usage 1
      ;;
  esac
done

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
section() { echo; bold "=== $* ==="; }

section "Repo root: $ROOT"

section "Archivos *.tfvars"
found_tfvars=0
while IFS= read -r -d '' f; do
  if [[ -n "$ENV_FILTER" ]]; then
    base="$(basename "$f")"
    [[ "$base" == "${ENV_FILTER}.tfvars" || "$base" == "${ENV_FILTER}.tfvars.example" ]] || continue
  fi
  if grep -qiE '(postgres|"username"[[:space:]]*:[[:space:]]*"postgres")' "$f" 2>/dev/null; then
    found_tfvars=1
    echo "--- $f ---"
    grep -niE 'postgres|username' "$f" || true
  fi
done < <(find "$ROOT" \( -name '*.tfvars' -o -name '*.tfvars.example' \) -not -path '*/.terraform/*' -print0 2>/dev/null)
[[ $found_tfvars -eq 0 ]] && echo "(sin coincidencias)"

section "Archivos outputs.tf"
found_outputs=0
while IFS= read -r -d '' f; do
  if grep -qi postgres "$f" 2>/dev/null; then
    found_outputs=1
    echo "--- $f ---"
    grep -ni postgres "$f" || true
  fi
done < <(find "$ROOT" -name 'outputs.tf' -not -path '*/.terraform/*' -print0 2>/dev/null)
[[ $found_outputs -eq 0 ]] && echo "(sin coincidencias)"

if [[ $RUN_TF_OUTPUT -eq 1 && -d "$TF_DIR" ]]; then
  section "terraform output ($TF_DIR)"
  if command -v terraform >/dev/null 2>&1; then
    (
      cd "$TF_DIR"
      [[ -f ./bin/tf-env.sh ]] && source ./bin/tf-env.sh 2>/dev/null || true
      if terraform output -json >/dev/null 2>&1; then
        out="$(terraform output -json)"
        if echo "$out" | grep -qi postgres; then
          echo "$out" | python3 -c "
import json, sys
for k, v in json.load(sys.stdin).items():
    b = json.dumps(v)
    if 'postgres' in b.lower():
        print(f'{k}: {b}')
" 2>/dev/null || echo "$out" | grep -i postgres
        else
          echo "(sin 'postgres' en output)"
        fi
      else
        echo "No se pudo leer output (init/workspace)."
      fi
    )
  else
    echo "terraform no está en PATH."
  fi
fi

section "Repo (username postgres en tf, json, py, yml, md)"
USER_RE='"username"[[:space:]]*:[[:space:]]*"postgres"|username[[:space:]]*=[[:space:]]*"postgres"|MasterUsername.*postgres'
if command -v rg >/dev/null 2>&1; then
  rg -ni --glob '!**/.terraform/**' --glob '!**/.git/**' \
    --glob '*.tfvars*' --glob '*.tf' --glob '*.json' \
    --glob '*.py' --glob '*.yml' --glob '*.yaml' --glob '*.md' \
    "$USER_RE" "$ROOT" 2>/dev/null | head -80 || echo "(sin coincidencias)"
else
  grep -rniE "$USER_RE" \
    --include='*.tfvars*' --include='*.tf' --include='*.json' \
    --include='*.py' --include='*.yml' --include='*.yaml' --include='*.md' \
    "$ROOT" 2>/dev/null | grep -v '.terraform' | head -80 || echo "(sin coincidencias)"
fi

echo
bold "Listo."
