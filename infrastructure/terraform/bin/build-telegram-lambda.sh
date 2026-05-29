#!/usr/bin/env bash
set -euo pipefail

LAMBDA_DIR="${1:?lambda dir}"
OUT_ZIP="${2:?output zip}"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

REPO_ROOT="$(cd "${LAMBDA_DIR}/../../.." && pwd)"

python3 -m pip install -q -r "${LAMBDA_DIR}/requirements.txt" -t "${BUILD_DIR}" --upgrade
cp "${LAMBDA_DIR}"/*.py "${BUILD_DIR}/"
mkdir -p "${BUILD_DIR}/src"
cp -R "${REPO_ROOT}/src/dao" "${REPO_ROOT}/src/services" "${REPO_ROOT}/src/scoring" "${REPO_ROOT}/src/utils" "${REPO_ROOT}/src/kb" "${REPO_ROOT}/src/web" "${REPO_ROOT}/src/fixtures" "${REPO_ROOT}/src/jobs" "${REPO_ROOT}/src/clients" "${BUILD_DIR}/src/"
touch "${BUILD_DIR}/src/__init__.py"

mkdir -p "$(dirname "$OUT_ZIP")"
OUT_ZIP="$(cd "$(dirname "$OUT_ZIP")" && pwd)/$(basename "$OUT_ZIP")"
rm -f "$OUT_ZIP"
(cd "$BUILD_DIR" && zip -qr "$OUT_ZIP" .)

echo "Created ${OUT_ZIP}"
