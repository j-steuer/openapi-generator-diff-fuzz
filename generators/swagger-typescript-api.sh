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
  -t telephuzz:swagger-typescript-api \
  -f "$SCRIPT_DIR/dockerfiles/swagger-typescript-api.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

echo "Swagger TypeScript API: Generating TypeScript"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PROJECT_ROOT:/local" \
  -v "$OUTPUT_PATH:/local/output" \
  telephuzz:swagger-typescript-api \
  generate \
  -o /local/output \
  -n swagger-typescript-api.ts \
  -p /local/spec/openapi.json \
  --axios