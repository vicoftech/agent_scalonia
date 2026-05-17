#!/usr/bin/env bash
set -euo pipefail

LAMBDA_DIR="${1:?lambda dir}"
OUT_ZIP="${2:?output zip}"

BUILD_DIR="$(mktemp -d)"
trap 'rm -rf "$BUILD_DIR"' EXIT

python3 -m pip install -q -r "${LAMBDA_DIR}/requirements.txt" -t "${BUILD_DIR}" --upgrade
cp "${LAMBDA_DIR}/handler.py" "${BUILD_DIR}/"

mkdir -p "$(dirname "$OUT_ZIP")"
OUT_ZIP="$(cd "$(dirname "$OUT_ZIP")" && pwd)/$(basename "$OUT_ZIP")"
rm -f "$OUT_ZIP"
(cd "$BUILD_DIR" && zip -qr "$OUT_ZIP" .)

echo "Created ${OUT_ZIP}"
