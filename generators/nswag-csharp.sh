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
  -t telephuzz:nswag \
  -f "$SCRIPT_DIR/dockerfiles/nswag.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

echo "Nswag: Generating C#"

docker run --rm \
  -v "$PROJECT_ROOT:/local" \
  -v "$OUTPUT_PATH:/local/output" \
  telephuzz:nswag \
  openapi2csclient \
  /input:/local/spec/openapi.json \
  /output:/local/output/nswag-csharp-client.cs \
  /namespace:MyCompany.ApiClient \
  /className:{controller}Client