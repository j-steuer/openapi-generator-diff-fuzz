SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker build \
  -t telephuzz:openapi-python-client \
  -f "$SCRIPT_DIR/dockerfiles/openapi-python-client.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

docker run --rm -v $(pwd):/local telephuzz:openapi-python-client generate --path /local/spec/openapi.json --output-path /local/clients/openapi-python-client --overwrite