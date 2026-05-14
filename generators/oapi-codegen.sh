SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker build \
  -t telephuzz:oapi-codegen \
  -f "$SCRIPT_DIR/dockerfiles/oapi-codegen.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

docker run --rm -v $(pwd):/local telephuzz:oapi-codegen -generate types,client -o "/local/clients/oapi-codegen-client.go" -package client /local/spec/openapi.json