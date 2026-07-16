#!/usr/bin/env bash

# basic client used for testing purposes, do NOT use for fuzzing

set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <output_path>"
    exit 1
fi

# Directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

SRC="$SCRIPT_DIR/../tests/testfiles/test_clients/basic_faulty_client"

# Resolve the output path to an absolute path
DEST="$(realpath -m "$1")"

# Create the destination parent directory if it doesn't exist
mkdir -p "$(dirname "$DEST")"

# Copy the directory recursively
cp -r "$SRC" "$DEST"

echo "Copied:"
echo "  $SRC"
echo "to:"
echo "  $DEST"