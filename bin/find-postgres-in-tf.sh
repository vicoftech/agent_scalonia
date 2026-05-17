#!/usr/bin/env bash
# Alias del script principal (mismo comportamiento).
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "${ROOT_DIR}/find-postgres.sh" "$@"
