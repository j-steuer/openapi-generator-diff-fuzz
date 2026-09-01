#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <language> <output-path>"
    exit 1
fi

LANG="$1"
OUT_DIR="$(realpath -m "$2")"

PARENT_DIR="$(dirname "$OUT_DIR")"
OUT_NAME="$(basename "$OUT_DIR")"

mkdir -p "$PARENT_DIR"

echo "Swagger Codegen: Generating $LANG"
echo "Output: $OUT_DIR"

docker run --rm \
    --user "$(id -u):$(id -g)" \
    -v "$(pwd)":/local \
    -v "$PARENT_DIR":/output \
    swaggerapi/swagger-codegen-cli-v3.0.82 \
    generate \
    -i /local/spec/openapi.json \
    -l "$LANG" \
    -o "/output/$OUT_NAME"

# C# post-processing: flatten src/IO.Swagger
if [ "$LANG" = "csharp" ]; then
    echo "Post-processing C# output structure..."

    SRC_DIR="$OUT_DIR/src/IO.Swagger"
    TMP_DIR="${OUT_DIR}_temp"

    if [ -d "$SRC_DIR" ]; then
        mv "$SRC_DIR" "$TMP_DIR"
        rm -rf "$OUT_DIR"
        mv "$TMP_DIR" "$OUT_DIR"
    else
        echo "Directory $SRC_DIR does not exist"
    fi
fi