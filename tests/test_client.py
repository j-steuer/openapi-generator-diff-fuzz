"""Tests for client libraries."""

from pathlib import Path

import docker
import pytest
from requests.models import CaseInsensitiveDict

from telephuzz.http_message import HTTPMethod, Request
from telephuzz.session.client_library import (
    ClientLibraryContainer,
    OapiGeneratorCLC,
    OpenAPIGenGoCLC,
    OpenAPIGenPythonCLC,
    OpenAPIGenTypeScriptCLC,
    OpenapiPythonGeneratorCLC,
    SwaggerCodegenPythonCLC,
    SwaggerCodegenTypeScriptCLC,
)

CLIENT_PATH = Path(__file__).resolve().parent / "testfiles" / "clients"


def _init_and_send(clc: ClientLibraryContainer, api: str):
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

    response = clc.send(request, api)
    assert isinstance(response, str)
    assert "Hello Alice, you are 30 years old!" in response


def test_client_openapigen_python(api) -> None:
    """Test that default clients initialize correctly."""
    library_path = CLIENT_PATH / "openapi-gen-python-client"

    with OpenAPIGenPythonCLC(library_path=library_path) as clc:
        _init_and_send(clc, api)


def test_client_openapigen_go(api) -> None:
    """Test that default clients initialize correctly."""
    library_path = CLIENT_PATH / "openapi-gen-go-client"

    with OpenAPIGenGoCLC(library_path=library_path) as clc:
        _init_and_send(clc, api)


def test_oapi_codegen(api) -> None:
    """Test that default clients initialize correctly."""
    library_path = CLIENT_PATH / "oapi-codegen-client.go"

    with OapiGeneratorCLC(library_path=library_path) as clc:
        _init_and_send(clc, api)


def test_client_openapigen_typescript(api) -> None:
    """Test that default clients initialize correctly."""
    library_path = CLIENT_PATH / "openapi-gen-typescript-axios-client"

    with OpenAPIGenTypeScriptCLC(library_path=library_path) as clc:
        _init_and_send(clc, api)


def test_client_swaggergen_python(api) -> None:
    """Test that default clients initialize correctly."""
    library_path = CLIENT_PATH / "swagger-codegen-python-client"

    with SwaggerCodegenPythonCLC(library_path=library_path) as clc:
        _init_and_send(clc, api)


def test_swaggergen_typescript(api) -> None:
    """Test that default clients initialize correctly."""
    library_path = CLIENT_PATH / "swagger-codegen-typescript-axios-client"

    with SwaggerCodegenTypeScriptCLC(library_path=library_path) as clc:
        _init_and_send(clc, api)


def test_client_openapi_python_generator(api) -> None:
    """Test that default clients initialize correctly."""
    library_path = CLIENT_PATH / "openapi-python-client"

    with OpenapiPythonGeneratorCLC(library_path=library_path) as clc:
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
