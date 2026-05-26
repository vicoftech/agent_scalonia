#!/usr/bin/env bash
# SPEC-032 / SPEC-031 — Terraform deja estos flags en false por defecto. Si DEV_TFVARS
# no los define, el apply CI no crea Lambdas/collector/schedules match_lifecycle.
#
# Si ya existe una línea (no comentada) enable_match_schedules = … no modificamos.

set -euo pipefail

TFVARS_FILE="${1:?path to *.tfvars}"
WS="${TF_WORKSPACE:-dev}"

if [[ "${WS}" != "dev" ]]; then
  exit 0
fi

if [[ ! -f "${TFVARS_FILE}" ]]; then
  echo "WARN: tfvars missing: ${TFVARS_FILE}" >&2
  exit 0
fi

if grep -qE '^[[:space:]]*enable_match_schedules[[:space:]]*=' "${TFVARS_FILE}"; then
  exit 0
fi

{
  echo ''
  echo '# SPEC-031/SPEC-032 — inyectado por CI (faltaban en DEV_TFVARS)'
  echo 'enable_result_queues     = true'
  echo 'enable_result_collector  = true'
  echo 'enable_match_schedules   = true'
} >>"${TFVARS_FILE}"

echo "Added SPEC-032 flags to ${TFVARS_FILE} (workspace=dev)"
