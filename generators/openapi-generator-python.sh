docker run --rm -v $(pwd):/local openapitools/openapi-generator-cli:v7.22.0 generate   -i /local/spec/openapi.json   -g python   -o /local/clients/openapi-gen-python-client
