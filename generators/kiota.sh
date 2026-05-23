SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
docker build \
  -t telephuzz:kiota \
  -f "$SCRIPT_DIR/dockerfiles/kiota.dockerfile" \
  "$SCRIPT_DIR/dockerfiles"

LANG="python"
echo "Kiota: Generating $LANG"

OUT_DIR="/local/clients/kiota-$LANG-client"

docker run --rm \
  -v "$(pwd)":/local \
  telephuzz:kiota \
  generate --language "$LANG" --openapi /local/spec/openapi.json --output /local/clients/kiota-$LANG-client/my_kiota_client -c PostsClient -n client --clean-output

cp "$SCRIPT_DIR/kiota_project_files/pyproject.toml" "clients/kiota-python-client/pyproject.toml"
find clients/kiota-python-client/my_kiota_client -type d -exec touch {}/__init__.py \;


LANG="csharp"
echo "Kiota: Generating $LANG"

OUT_DIR="/local/clients/kiota-$LANG-client"

docker run --rm \
  -v "$(pwd)":/local \
  telephuzz:kiota \
  generate --language "$LANG" --openapi /local/spec/openapi.json --output /local/clients/kiota-$LANG-client/my_kiota_client -c PostsClient -n client --clean-output

cp "$SCRIPT_DIR/kiota_project_files/MyKiotaClient.csproj" "clients/kiota-csharp-client/Client.csproj"


LANG="java"
echo "Kiota: Generating $LANG"

OUT_DIR="/local/clients/kiota-$LANG-client"

docker run --rm \
  -v "$(pwd)":/local \
  telephuzz:kiota \
  generate --language "$LANG" --openapi /local/spec/openapi.json --output /local/clients/kiota-$LANG-client/client -c PostsClient -n client --clean-output

cp "$SCRIPT_DIR/kiota_project_files/pom.xml" "clients/kiota-java-client/pom.xml"