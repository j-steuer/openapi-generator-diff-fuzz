"""Tests for client libraries."""

from pathlib import Path

import docker
import pytest
from docker.errors import NotFound

from telephuzz.http_message import HTTPMethod, Request
from telephuzz.session.client_library import OpenAPIGenPythonCLC

OPENAPI_GEN_PYTHON_PATH = (
    Path(__file__).resolve().parent
    / "testfiles"
    / "clients"
    / "openapi-gen-python-client"
)


# TODO assert that other containers are untouched
def test_client_init() -> None:
    """Test that default clients initialize correctly."""
    library_path = OPENAPI_GEN_PYTHON_PATH
    client = docker.from_env()
    from datetime import datetime

    with OpenAPIGenPythonCLC(library_path=library_path) as clc:
        # check that container is running
        assert clc.container is not None
        id = clc.container.id
        assert id is not None
        container = client.containers.get(id)
        assert container.status == "running"
        before = datetime.now()
    print("DEBUG:", datetime.now() - before)
    # check that container was stopped
    with pytest.raises(NotFound):
        client.containers.get(id)


def test_client_send(api: str, basic_request: Request) -> None:
    """Test sending a message with the client to an API."""
    library_path = OPENAPI_GEN_PYTHON_PATH

    # create request
    basic_request.path = "/greet"
    basic_request.method = HTTPMethod("GET")
    basic_request.query_parameters = {"name": "Alice", "age": 30}

    with OpenAPIGenPythonCLC(library_path=library_path) as clc:
        print(clc.send(basic_request, api))
