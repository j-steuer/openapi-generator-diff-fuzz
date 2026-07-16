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
  -t telephuzz:oapi-codegen \
  -f "$SCRIPT_DIR/dockerfiles/oapi-codegen.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PROJECT_ROOT:/local" \
  -v "$OUTPUT_PATH:/local/output" \
  telephuzz:oapi-codegen \
  -generate types,client \
  -o "/local/output/oapi-codegen-client.go" \
  -package client \
  /local/spec/openapi.json