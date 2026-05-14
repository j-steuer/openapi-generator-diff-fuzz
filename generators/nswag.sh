SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker build \
  -t telephuzz:nswag \
  -f "$SCRIPT_DIR/dockerfiles/nswag.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

echo "Nswag: Generating TypeScript Axios"
docker run --rm -v $(pwd):/local telephuzz:nswag openapi2tsclient \
  /input:/local/spec/openapi.json \
  /output:/local/clients/nswag-typescript-client.ts \
  /template:Axios \
  /className:{controller}Client

echo "Nswag: Generating C#"
docker run --rm -v $(pwd):/local telephuzz:nswag openapi2csclient \
  /input:/local/spec/openapi.json \
  /output:/local/clients/nswag-csharp-client.cs \
  /namespace:MyCompany.ApiClient \
  /className:{controller}Client