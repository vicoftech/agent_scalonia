#!/usr/bin/env bash
# Empaqueta agent/ + src/ + dependencias para AgentCore Runtime (Linux ARM64).
set -euo pipefail

REPO_ROOT="${1:?repo root}"
OUT_ZIP="${2:?output zip path}"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

echo "Building agent package for Linux ARM64 in ${BUILD_DIR}"

# AgentCore Runtime solo acepta arm64 (Graviton). pip en macOS instala *-darwin.so → CREATE_FAILED.
python3 -m pip install -q -r "${REPO_ROOT}/requirements-agent.txt" -t "${BUILD_DIR}" --upgrade \
  --platform manylinux2014_aarch64 \
  --python-version 3.12 \
  --implementation cp \
  --only-binary=:all:

cp -R "${REPO_ROOT}/agent" "${REPO_ROOT}/src" "${BUILD_DIR}/"
find "${BUILD_DIR}" -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true

mkdir -p "$(dirname "$OUT_ZIP")"
OUT_ZIP="$(cd "$(dirname "$OUT_ZIP")" && pwd)/$(basename "$OUT_ZIP")"
rm -f "$OUT_ZIP"
(cd "$BUILD_DIR" && zip -qr "$OUT_ZIP" .)

echo "Created ${OUT_ZIP} ($(du -h "$OUT_ZIP" | cut -f1))"
