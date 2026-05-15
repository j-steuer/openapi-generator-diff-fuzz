SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker build \
  -t telephuzz:swift-openapi-generator \
  -f "$SCRIPT_DIR/dockerfiles/swift-openapi-generator.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

echo "Swift OpenAPI Generator: Generating Swift5"
docker run --rm \
  -v "$(pwd)":/local \
  telephuzz:swift-openapi-generator \
  generate /local/spec/openapi.json \
  --mode client \
  --output-directory /local/clients/swift-openapi-generator