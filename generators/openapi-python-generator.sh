#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <output-path>"
  exit 1
fi

OUTPUT_PATH="$(realpath "$1")"
PROJECT_ROOT="$(pwd)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker build \
  -t telephuzz:openapi-python-client \
  -f "$SCRIPT_DIR/dockerfiles/openapi-python-client.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

docker run --rm \
  -v "$PROJECT_ROOT:/local" \
  -v "$OUTPUT_PATH:/local/output" \
  telephuzz:openapi-python-client \
  generate \
  --path /local/spec/openapi.json \
  --output-path /local/output \
  --overwrite