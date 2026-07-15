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
  -t telephuzz:kiota \
  -f "$SCRIPT_DIR/dockerfiles/kiota.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

echo "Kiota: Generating java"

docker run --rm \
  -v "$PROJECT_ROOT:/local" \
  -v "$OUTPUT_PATH:/local/output" \
  telephuzz:kiota \
  generate \
  --language java \
  --openapi /local/spec/openapi.json \
  --output /local/output/client \
  -c PostsClient \
  -n client \
  --clean-output

cp "$SCRIPT_DIR/kiota_project_files/pom.xml" \
  "$OUTPUT_PATH/pom.xml"