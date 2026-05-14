#!/usr/bin/env bash

set -e

LANGS=("python" "go" "java" "swift5" "csharp" "typescript-axios")

for LANG in "${LANGS[@]}"; do
  echo "Swagger Codegen: Generating $LANG"

  docker run --rm -v $(pwd):/local swaggerapi/swagger-codegen-cli-v3 generate -i /local/spec/openapi.json -l "$LANG" -o /local/clients/swagger-codegen-$LANG-client

done