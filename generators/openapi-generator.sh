#!/usr/bin/env bash

set -e

LANGS=("python" "go" "java")

for LANG in "${LANGS[@]}"; do
  echo "OpenAPI Generator: Generating $LANG"

  docker run --rm \
    -v "$(pwd)":/local \
    openapitools/openapi-generator-cli:v7.22.0 \
    generate \
    -i /local/spec/openapi.json \
    -g "$LANG" \
    -o "/local/clients/openapi-gen-$LANG-client"

done