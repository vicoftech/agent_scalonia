#!/usr/bin/env bash
# Empaqueta kb_ingest / kb_query: handler + src/kb (Linux x86_64).
set -euo pipefail

REPO_ROOT="${1:?repo root}"
LAMBDA_NAME="${2:?kb_ingest|kb_query|kb_enrichment_dispatcher}"
OUT_ZIP="${3:?output zip}"

LAMBDA_DIR="${REPO_ROOT}/infrastructure/lambdas/${LAMBDA_NAME}"
BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

python3 -m pip install -q --no-cache-dir \
  -r "${LAMBDA_DIR}/requirements.txt" \
  -t "${BUILD_DIR}" \
  --upgrade \
  --platform manylinux2014_x86_64 \
  --python-version 3.12 \
  --implementation cp \
  --only-binary=:all:

cp "${LAMBDA_DIR}/handler.py" "${BUILD_DIR}/"
mkdir -p "${BUILD_DIR}/src"
cp -R "${REPO_ROOT}/src/kb" "${BUILD_DIR}/src/"
touch "${BUILD_DIR}/src/__init__.py"
find "${BUILD_DIR}" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

mkdir -p "$(dirname "$OUT_ZIP")"
OUT_ZIP="$(cd "$(dirname "$OUT_ZIP")" && pwd)/$(basename "$OUT_ZIP")"
rm -f "$OUT_ZIP"
(cd "${BUILD_DIR}" && zip -qr "${OUT_ZIP}" .)
echo "Created ${OUT_ZIP}"
