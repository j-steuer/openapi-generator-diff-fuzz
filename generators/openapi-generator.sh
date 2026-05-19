#!/usr/bin/env bash

set -e

LANGS=("python" "go" "java" "swift5" "csharp" "typescript-axios")

for LANG in "${LANGS[@]}"; do
  echo "OpenAPI Generator: Generating $LANG"

  OUT_DIR="/local/clients/openapi-gen-$LANG-client"

  docker run --rm \
    -v "$(pwd)":/local \
    openapitools/openapi-generator-cli:v7.22.0 \
    generate \
    -i /local/spec/openapi.json \
    -g "$LANG" \
    -o "$OUT_DIR"

  # --- C# post-processing: flatten src/Org.OpenAPITools ---
  if [ "$LANG" = "csharp" ]; then
    echo "Post-processing C# output structure..."

    OUT_DIR="clients/openapi-gen-csharp-client"
    TMP_DIR="clients/openapi-gen-csharp-client_temp"
    SRC_DIR="clients/openapi-gen-csharp-client/src/Org.OpenAPITools"
    
  if [ -e "$SRC_DIR" ]; then
      echo "Moving contents of $SRC_DIR to $OUT_DIR"

      mv "$SRC_DIR" "$TMP_DIR"
      rm -r "$OUT_DIR"
      mv "$TMP_DIR" "$OUT_DIR"

  else
      echo "File $SRC_DIR does not exist"
  fi
fi

done