SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker build \
  -t telephuzz:orval \
  -f "$SCRIPT_DIR/dockerfiles/orval.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

docker run --rm -v $(pwd):/local telephuzz:orval \
  --input /local/spec/openapi.json \
  --output /local/clients/orval.ts \
  --client axios