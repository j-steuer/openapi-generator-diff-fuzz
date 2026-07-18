#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <output-path>"
  exit 1
fi

OUTPUT_PATH="$1"
PROJECT_ROOT="$(pwd)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

docker build \
  -t telephuzz:kiota \
  -f "$SCRIPT_DIR/dockerfiles/kiota.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

echo "Kiota: Generating python"

mkdir -p "$OUTPUT_PATH"

docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$PROJECT_ROOT:$PROJECT_ROOT" \
  -v "$OUTPUT_PATH:$OUTPUT_PATH" \
  -w "$PROJECT_ROOT" \
  telephuzz:kiota \
  generate \
  --language python \
  --openapi "$PROJECT_ROOT/spec/openapi.json" \
  --output "$OUTPUT_PATH/my_kiota_client" \
  -c PostsClient \
  -n client \
  --clean-output

cp "$SCRIPT_DIR/kiota_project_files/pyproject.toml" \
  "$OUTPUT_PATH/pyproject.toml"

find "$OUTPUT_PATH/my_kiota_client" -type d -exec touch {}/__init__.py \;