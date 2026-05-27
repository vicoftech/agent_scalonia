#!/usr/bin/env bash
# Empaqueta agent/ + src/{kb,dao,services,web,fixtures,jobs} para AgentCore Runtime (Linux ARM64).
set -euo pipefail

REPO_ROOT="${1:?repo root}"
OUT_ZIP="${2:?output zip path}"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "Building agent package for Linux ARM64 in ${BUILD_DIR}"

python3 -m pip install -q --no-cache-dir \
  -r "${REPO_ROOT}/requirements-agent.txt" \
  -t "${BUILD_DIR}" \
  --upgrade \
  --platform manylinux2014_aarch64 \
  --python-version 3.12 \
  --implementation cp \
  --only-binary=:all:

cp -R "${REPO_ROOT}/agent" "${BUILD_DIR}/"
mkdir -p "${BUILD_DIR}/src"
cp -R "${REPO_ROOT}/src/kb" "${REPO_ROOT}/src/dao" "${REPO_ROOT}/src/services" "${REPO_ROOT}/src/web" "${REPO_ROOT}/src/fixtures" "${REPO_ROOT}/src/jobs" "${BUILD_DIR}/src/"
touch "${BUILD_DIR}/src/__init__.py"
find "${BUILD_DIR}" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

mkdir -p "$(dirname "$OUT_ZIP")"
OUT_ZIP="$(cd "$(dirname "$OUT_ZIP")" && pwd)/$(basename "$OUT_ZIP")"
rm -f "$OUT_ZIP"
(cd "${BUILD_DIR}" && zip -qr "${OUT_ZIP}" .)

# Fallar si quedó algún binario macOS (causa CREATE_FAILED en AgentCore).
if unzip -l "${OUT_ZIP}" | grep -qiE 'darwin|macosx'; then
  echo "ERROR: el ZIP contiene binarios macOS — no usar en AgentCore ARM64" >&2
  exit 1
fi

SIZE="$(du -h "${OUT_ZIP}" | cut -f1)"
echo "Created ${OUT_ZIP} (${SIZE})"
