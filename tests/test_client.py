"""Tests for client libraries."""

import json
from pathlib import Path
from typing import cast

import pytest
from docker.models.containers import Container
from docker.models.networks import Network
from requests.models import CaseInsensitiveDict

from telephuzz.config import get_config
from telephuzz.http_message import HTTPMethod, Request
from telephuzz.invocation_data import InvocationData
from telephuzz.operation_ids import generate_operation_id
from telephuzz.session.client_library import (
    ClientLibraryContainer,
    KiotaCSharpCLC,
    KiotaPythonCLC,
    NswagCSharpCLC,
    NswagTypeScriptCLC,
    OapiGeneratorCLC,
    OpenAPIGenCsharpCLC,
    OpenAPIGenGoCLC,
    OpenAPIGenPythonCLC,
    OpenAPIGenTypeScriptCLC,
    OpenapiPythonGeneratorCLC,
    OperationIdBasedCLC,
    OrvalCLC,
    SwaggerCodegenCsharpCLC,
    SwaggerCodegenPythonCLC,
    SwaggerCodegenTypeScriptCLC,
    SwaggerTsAPICLC,
)

CLIENT_PATH = Path(__file__).resolve().parent / "testfiles" / "clients"
CLIENT_CASES_NO_AUTH = [
    OpenAPIGenCsharpCLC,
    OpenAPIGenGoCLC,
    OpenAPIGenPythonCLC,
    OpenAPIGenTypeScriptCLC,
    SwaggerCodegenCsharpCLC,
    SwaggerCodegenPythonCLC,
    SwaggerCodegenTypeScriptCLC,
    OapiGeneratorCLC,
    NswagCSharpCLC,
    NswagTypeScriptCLC,
    OrvalCLC,
    SwaggerTsAPICLC,
    OpenapiPythonGeneratorCLC,
    KiotaCSharpCLC,
    KiotaPythonCLC,
]


def test_from_id():
    """Test obtaining a class based on id."""
    client_type = ClientLibraryContainer.from_id("openapi-generator:python")
    assert client_type == OpenAPIGenPythonCLC


def test_get_method_name_opid_mixin(monkeypatch):
    """Test mixin for obtaining method names based on operation id."""
    config = get_config()

    with open("tests/testfiles/processed_petshop.json", "r") as f:
        spec = json.load(f)

    monkeypatch.setattr(config, "spec", spec)
    monkeypatch.setattr(config, "spec_str", json.dumps(spec))

    class Dummy(OperationIdBasedCLC):
        def _translate(
            self, invocation: InvocationData, api_path: str
        ) -> str | list[str]:
            return "DUMMY"

    mixin = Dummy.__new__(Dummy)

    request = Request(
        CaseInsensitiveDict(),
        body="",
        method=HTTPMethod.DELETE,
        path="/user/123",
        query_parameters={},
    )

    assert mixin._get_method_name(InvocationData(request)) == generate_operation_id(
        HTTPMethod.DELETE.value, "/user/{username}"
    )


@pytest.mark.parametrize("api_wfd", ["swagger-petstore"], indirect=True)
def test_client_openapi_gen_python_petshop(
    api_wfd: tuple[Network, str], monkeypatch
) -> None:
    """Test that client library works with one of the default test targets."""
    config = get_config()

    with open("tests/testfiles/processed_petshop.json", "r") as f:
        spec = json.load(f)

    monkeypatch.setattr(config, "spec", spec)
    monkeypatch.setattr(config, "spec_str", json.dumps(spec))

    network, api_path = api_wfd
    with OpenAPIGenPythonCLC() as clc:
        network.connect(cast(Container, clc.container))

        request = Request(
            headers=CaseInsensitiveDict(
                {
                    "Host": "localhost:8000",
                    "User-Agent": "schemathesis/4.15.2",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                    "X-Schemathesis-TestCaseId": "dPIEin",
                }
            ),
            body="",
            method=HTTPMethod.GET,
            path="/user/%C2%B4i%C2%84%C3%B2X2%C2%BA%3A%3D%C3%B5%F1%BA%86%8D",
            query_parameters={},
        )

        response = clc.send(InvocationData(request), api_path=api_path)
        assert isinstance(response, str)
        assert "User not found" in response
