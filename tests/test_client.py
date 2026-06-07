"""Tests for client libraries."""

from pathlib import Path

import docker
import pytest
from requests.models import CaseInsensitiveDict

from telephuzz.http_message import HTTPMethod, Request
from telephuzz.session.client_library import (
    ClientLibraryContainer,
    KiotaCSharpCLC,
    KiotaJavaCLC,
    KiotaPythonCLC,
    NswagCSharpCLC,
    NswagTypeScriptCLC,
    OapiGeneratorCLC,
    OpenAPIGenCsharpCLC,
    OpenAPIGeneratorSwiftCLC,
    OpenAPIGenGoCLC,
    OpenAPIGenJavaCLC,
    OpenAPIGenPythonCLC,
    OpenAPIGenTypeScriptCLC,
    OpenapiPythonGeneratorCLC,
    OrvalCLC,
    SwaggerCodegenCsharpCLC,
    SwaggerCodegenPythonCLC,
    SwaggerCodegenTypeScriptCLC,
    SwaggerTsAPICLC,
)

CLIENT_PATH = Path(__file__).resolve().parent / "testfiles" / "clients"
CLIENT_CASES_NO_AUTH = [
    (OpenAPIGenCsharpCLC, CLIENT_PATH / "openapi-gen-csharp-client"),
    (OpenAPIGenGoCLC, CLIENT_PATH / "openapi-gen-go-client"),
    (OpenAPIGenPythonCLC, CLIENT_PATH / "openapi-gen-python-client"),
    (OpenAPIGenTypeScriptCLC, CLIENT_PATH / "openapi-gen-typescript-axios-client"),
    (SwaggerCodegenCsharpCLC, CLIENT_PATH / "swagger-codegen-csharp-client"),
    (SwaggerCodegenPythonCLC, CLIENT_PATH / "swagger-codegen-python-client"),
    (
        SwaggerCodegenTypeScriptCLC,
        CLIENT_PATH / "swagger-codegen-typescript-axios-client",
    ),
    (OapiGeneratorCLC, CLIENT_PATH / "oapi-codegen-client.go"),
    (NswagCSharpCLC, CLIENT_PATH / "nswag-csharp-client.cs"),
    (NswagTypeScriptCLC, CLIENT_PATH / "nswag-typescript-client.ts"),
    (OrvalCLC, CLIENT_PATH / "orval.ts"),
    (SwaggerTsAPICLC, CLIENT_PATH / "swagger-typescript-api.ts"),
    (OpenapiPythonGeneratorCLC, CLIENT_PATH / "openapi-python-client"),
    (KiotaCSharpCLC, CLIENT_PATH / "kiota-csharp-client"),
    (KiotaPythonCLC, CLIENT_PATH / "kiota-python-client"),
]


def _init_and_send(clc: ClientLibraryContainer, api: str, auth: bool = False):
    client = docker.from_env()
    assert clc.container is not None
    id = clc.container.id
    assert id is not None
    container = client.containers.get(id)
    assert container.status == "running"

    request = Request(
        headers=CaseInsensitiveDict({"Test": ["test"]}),
        body=None,
        method=HTTPMethod.GET,
        path="dummytarget.org/test",
        query_parameters={},
    )
    request.path = "/greet"
    request.method = HTTPMethod("GET")
    request.query_parameters = {"name": "Alice", "age": 30}

    if auth:
        request.headers["Authorization"] = "mock-token"

    response = clc.send(request, api)
    assert isinstance(response, str)
    assert "Hello Alice, you are 30 years old!" in response


def test_from_id():
    """Test obtaining a class based on id."""
    client_type = ClientLibraryContainer.from_id("openapi-generator:python")
    assert client_type == OpenAPIGenPythonCLC


@pytest.mark.parametrize("clc_class, library_path", CLIENT_CASES_NO_AUTH)
def test_clients_noauth(clc_class, library_path, api) -> None:
    """Basic GET request test without authentication."""
    with clc_class(library_path=library_path) as clc:
        _init_and_send(clc, api, auth=False)


def test_client_openapigen_python_auth(api_oauth) -> None:
    """Test that default clients initialize correctly."""
    library_path = CLIENT_PATH / "openapi-gen-python-auth-client"

    with OpenAPIGenPythonCLC(library_path=library_path) as clc:
        _init_and_send(clc, api_oauth, auth=True)


@pytest.mark.skip("Fix")
def test_openapi_generator_java(api) -> None:
    """Test that default clients initialize correctly."""
    library_path = CLIENT_PATH / "openapi-gen-java-client"

    with OpenAPIGenJavaCLC(library_path=library_path) as clc:
        _init_and_send(clc, api)


@pytest.mark.skip(reason="Not compatible with Linux, will need its own setup on MacOS")
def test_openapi_generator_swift(api) -> None:
    """Test that default clients initialize correctly."""
    library_path = CLIENT_PATH / "openapi-gen-swift5-client"

    with OpenAPIGeneratorSwiftCLC(library_path=library_path) as clc:
        _init_and_send(clc, api)


@pytest.mark.skip("Implement")
def test_kiota_java(api) -> None:
    """Test that default clients initialize correctly."""
    library_path = CLIENT_PATH / "kiota-java-client"

    with KiotaJavaCLC(library_path=library_path) as clc:
        print("Container upsie doopsie")
        from time import sleep

        sleep(10000)
        _init_and_send(clc, api)


@pytest.mark.skip("TODO implement oauth support")
@pytest.mark.parametrize("api", ["auth"], indirect=True)
def test_client_auth(api: str, basic_request: Request) -> None:
    """Test sending a message with the client to an API."""
    library_path = CLIENT_PATH / "openapi-gen-python-client"

    # create request
    basic_request.path = "/greet"
    basic_request.method = HTTPMethod("GET")
    basic_request.query_parameters = {"name": "Alice", "age": 30}

    with OpenAPIGenPythonCLC(library_path=library_path) as clc:
        response = clc.send(basic_request, api)
        assert isinstance(response, str)
        assert "Hello Alice, you are 30 years old!" in response
