#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <output-path>"
  exit 1
fi

OUTPUT_PATH="$(realpath -m "$1")"
PROJECT_ROOT="$(pwd)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PARENT_DIR="$(dirname "$OUTPUT_PATH")"
OUT_NAME="$(basename "$OUTPUT_PATH")"

mkdir -p "$PARENT_DIR"

docker build \
  -t telephuzz:openapi-python-client \
  -f "$SCRIPT_DIR/dockerfiles/openapi-python-client.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PROJECT_ROOT:/local" \
  -v "$PARENT_DIR:/output" \
  telephuzz:openapi-python-client \
  generate \
  --path /local/spec/openapi.json \
  --output-path "/output/$OUT_NAME" \
  --overwrite