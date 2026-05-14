SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker build \
  -t telephuzz:swagger-typescript-api \
  -f "$SCRIPT_DIR/dockerfiles/swagger-typescript-api.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

echo "Swagger TypeScript API: Generating TypeScript"
docker run --rm -v $(pwd):/local telephuzz:swagger-typescript-api generate -o /local/clients -n swagger-typescript-api.ts -p /local/spec/openapi.json --axios