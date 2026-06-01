#!/usr/bin/env bash

set -e

LANGS=("python" "go" "java" "swift5" "csharp" "typescript-axios")

for LANG in "${LANGS[@]}"; do
  echo "Swagger Codegen: Generating $LANG"

  docker run --rm -v $(pwd):/local swaggerapi/swagger-codegen-cli-v3:3.0.80 generate -i /local/spec/openapi.json -l "$LANG" -o /local/clients/swagger-codegen-$LANG-client
  docker run --rm -v $(pwd):/local swaggerapi/swagger-codegen-cli-v3:3.0.80 generate -i /local/spec/openapi_auth.json -l "$LANG" -o /local/clients/swagger-codegen-$LANG-client-auth


  # --- C# post-processing: flatten src/IO.Swagger ---
  if [ "$LANG" = "csharp" ]; then
    echo "Post-processing C# output structure..."

    OUT_DIR="clients/swagger-codegen-csharp-client"
    TMP_DIR="clients/swagger-codegen-csharp-client_temp"
    SRC_DIR="clients/swagger-codegen-csharp-client/src/IO.Swagger"

    OUT_DIR_AUTH="clients/swagger-codegen-csharp-client-auth"
    TMP_DIR_AUTH="clients/swagger-codegen-csharp-client_temp-auth"
    SRC_DIR="clients/swagger-codegen-csharp-client-auth/src/IO.Swagger"
    
  if [ -e "$SRC_DIR" ]; then
      echo "Moving contents of $SRC_DIR to $OUT_DIR"

      mv "$SRC_DIR" "$TMP_DIR"
      rm -r "$OUT_DIR"
      mv "$TMP_DIR" "$OUT_DIR"

  else
      echo "File $SRC_DIR does not exist"
  fi

  if [ -e "$SRC_DIR_AUTH" ]; then
      echo "Moving contents of $SRC_DIR_AUTH to $OUT_DIR_AUTH"

      mv "$SRC_DIR_AUTH" "$TMP_DIR_AUTH"
      rm -r "$OUT_DIR_AUTH"
      mv "$TMP_DIR_AUTH" "$OUT_DIR_AUTH"

  else
      echo "File $SRC_DIR_AUTH does not exist"
  fi
fi
done