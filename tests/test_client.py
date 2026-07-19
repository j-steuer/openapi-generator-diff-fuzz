"""Tests for client libraries."""

import json
import re
import tomllib
from copy import deepcopy
from pathlib import Path

import pytest
from conftest import TEST_CONFIG_BASE_PATH
from docker.models.networks import Network
from requests.models import CaseInsensitiveDict

from telephuzz.config import Config, get_config
from telephuzz.constants import BASE_PATH
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
    OpenAPIPythonClientCLC,
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
    OpenAPIPythonClientCLC,
    KiotaCSharpCLC,
    KiotaPythonCLC,
]


def _test_send_request(
    clc: ClientLibraryContainer,
    request: Request,
    network: Network,
    api_path: str,
    expected_response: str | None = None,
    exclude_str: list[str] | None = None,
    expected_status: int | None = None,
):
    """Test sending the request."""
    assert clc.container is not None

    network.connect(clc.container)

    response = clc.send(InvocationData(request), api_path=api_path)
    network.reload()
    assert isinstance(response, str)
    if expected_response is not None:
        assert expected_response in response
    if exclude_str:
        for string in exclude_str:
            assert string not in response
    if expected_status:
        # obtain status from mitmproxy logs
        network.reload()
        mitmproxy = [
            c
            for c in network.containers
            if c.image is not None and "mitmproxy" in c.image.tags[0]
        ][0]
        logs = mitmproxy.logs().decode()
        latest_status = re.findall(r"<< [0-9]{3}", logs)[-1]
        assert f"<< {expected_status}" == latest_status

    network.disconnect(clc.container)


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


def test_version_overwrite() -> None:
    """Spec version should be overwritten for clients that use it for generation."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    with OpenAPIPythonClientCLC() as _:
        clients_dir = BASE_PATH / "clients"
        client_dir = next(d for d in clients_dir.iterdir() if d.is_dir())
        with open(client_dir / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)

        assert "SNAPSHOT" not in data["tool"]["poetry"]["version"]


@pytest.mark.parametrize(
    "clc_class",
    [
        OpenAPIGenPythonCLC,
        SwaggerCodegenPythonCLC,
        OpenAPIPythonClientCLC,
        KiotaPythonCLC,
    ],
)
@pytest.mark.parametrize("api_wfd", ["swagger-petstore"], indirect=True)
def test_client_basic_petshop(clc_class, api_wfd: tuple[Network, str]) -> None:
    """Test that client library works with one of the default test targets."""

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

    network, api_path = api_wfd
    with clc_class() as clc:
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

        _test_send_request(clc, request, network, api_path, expected_status=404)


@pytest.mark.parametrize(
    "clc_class",
    [OpenAPIGenPythonCLC, SwaggerCodegenPythonCLC, OpenAPIPythonClientCLC],
)
@pytest.mark.parametrize("api_wfd", ["swagger-petstore"], indirect=True)
def test_resolve_path_params(clc_class, api_wfd: tuple[Network, str]):

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

    network, api_path = api_wfd
    with clc_class() as clc:
        request_int = Request(
            headers=CaseInsensitiveDict(
                {
                    "Host": "localhost:8000",
                    "User-Agent": "schemathesis/4.15.2",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                    "api_key": "l",
                    "X-Schemathesis-TestCaseId": "GGvhsb",
                }
            ),
            body="",
            method=HTTPMethod.GET,
            path="/pet/105",
            query_parameters={},
        )

        request_str = Request(
            headers=CaseInsensitiveDict(
                {
                    "Host": "localhost:8000",
                    "User-Agent": "schemathesis/4.15.2",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                    "api_key": "l",
                    "X-Schemathesis-TestCaseId": "GGvhsb",
                }
            ),
            body="",
            method=HTTPMethod.GET,
            path="/user/105",
            query_parameters={},
        )

        _test_send_request(clc, request_int, network, api_path, "Pet not found")
        _test_send_request(clc, request_str, network, api_path, "User not found")


@pytest.mark.parametrize(
    "clc_class", [OpenAPIGenPythonCLC, SwaggerCodegenPythonCLC, OpenAPIPythonClientCLC]
)
@pytest.mark.parametrize("api_wfd", ["swagger-petstore"], indirect=True)
def test_query_and_body(clc_class, api_wfd: tuple[Network, str]):
    """Test request with path variables and body."""

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

    network, api_path = api_wfd
    with clc_class() as clc:
        request = Request(
            headers=CaseInsensitiveDict(
                {
                    "Host": "localhost:8000",
                    "User-Agent": "schemathesis/4.15.2",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                    "X-Schemathesis-TestCaseId": "nwZmwH",
                    "Content-Type": "application/json",
                    "Content-Length": "2",
                }
            ),
            body="{}",
            method=HTTPMethod.PUT,
            path="/user/%C2%A6g%F4%84%82%90%C2%BB%C2%8F%C2%80%0Cr",
            query_parameters={},
        )

        _test_send_request(clc, request, network, api_path, "User not found")


@pytest.mark.parametrize(
    "clc_class", [OpenAPIGenPythonCLC, SwaggerCodegenPythonCLC, OpenAPIPythonClientCLC]
)
@pytest.mark.parametrize("api_wfd", ["swagger-petstore"], indirect=True)
def test_parse_invalid_python_json(clc_class, api_wfd: tuple[Network, str]):
    """Test parsing a JSON body not parseable through literal_eval."""

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

    network, api_path = api_wfd
    with clc_class() as clc:
        request = Request(
            headers=CaseInsensitiveDict(
                {
                    "Host": "localhost:8000",
                    "User-Agent": "schemathesis/4.15.2",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                    "X-Schemathesis-TestCaseId": "JXLuUJ",
                    "Content-Type": "application/json",
                    "Content-Length": "931",
                }
            ),
            body=(
                '{"name": "\\u00ea\\u0096h\\u00a5\\u00b9\\u00ae?1", "photoUrls": '
                '["\\udb62\\uddc9=b\\ud96f\\udd08", "P\\u00a6\\u00fc"], "id": -5008, '
                '"": 5.960464477539063e-08, "tags": [{"id": -1247184487}, {"name": '
                '"\\u00ee\\u00d7\\uda61\\udf05\\u009e~\\u00dfYA\\udb99\\udf03'
                '\\udbee\\ude6e\\udb84\\ude429\\udb12\\uddf2", '
                '"\\u00c1A\\"\\u0015\\u0016\\u0098\\u00d3\\u0000\\u0098\\u00f0'
                '\\udbfe\\ude7d\\t\\u00d5": {}, "id": 2843, "\\u008d\\u00bd": '
                '[{}, false, [false]]}, {"id": -562949953421312, "": '
                '[[5.8196220103433455e-307, "Vt\\u0002v\\u00b1", null]], "\\u001a": '
                '{"\\u0082\\ud82b\\udf11\\u00ef\\u1d20`f\\u00e2\\u00d7": {}, '
                '"\\u0087\\u009e\\u00a9\\u00d6\\u0081T": {'
                '"\\u0087\\u00cb\\ud98c\\udde2\\u00d4\\u0099\\u000e\\u008b'
                "\\u00f8\\u0017\\u0012\\u00da0:\\u00d3\\u00b2\\uda5b\\udc33"
                "\\ud915\\udd65\\u0088Z\\udbf5\\udf1c?\\ud9b7\\udfd2n"
                '\\ud870\\udf92\\u00a3\\u009d\\u0091": "=o\\u00e99", '
                '"\\u00c3O\\u0015\\udac6\\udcba\\ud8e7\\udd34": null}, '
                '"\\u0083\\u00c7\\u00c3\\u000b\\u009b\\u00fcT\\u0088\\u00fe": '
                '{"&\\u0097O\\u00ff": null}}}], "c\\u00df\\u00c8": ""}'
            ),
            method=HTTPMethod.POST,
            path="/pet",
            query_parameters={},
        )

        _test_send_request(clc, request, network, api_path, "-5008", ["Traceback"])


@pytest.mark.parametrize(
    "clc_class", [OpenAPIGenPythonCLC, SwaggerCodegenPythonCLC, OpenAPIPythonClientCLC]
)
@pytest.mark.parametrize("api_wfd", ["swagger-petstore"], indirect=True)
def test_json_body_array(clc_class, api_wfd: tuple[Network, str]):
    """Test request with path variables and body."""

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

    network, api_path = api_wfd
    with clc_class() as clc:
        request_empty = Request(
            headers=CaseInsensitiveDict(
                {
                    "Host": "localhost:8000",
                    "User-Agent": "schemathesis/4.15.2",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                    "X-Schemathesis-TestCaseId": "rD5pQN",
                    "Content-Type": "application/json",
                    "Content-Length": "2",
                }
            ),
            body="[]",
            method=HTTPMethod.POST,
            path="/user/createWithList",
            query_parameters={},
        )

        request_two = deepcopy(request_empty)
        request_two.body = json.dumps(
            [
                {
                    "id": 10,
                    "username": "theUser",
                    "firstName": "John",
                    "lastName": "James",
                    "email": "john@email.com",
                    "password": "12345",
                    "phone": "12345",
                    "userStatus": 1,
                }
            ]
        )

        _test_send_request(
            clc,
            request_empty,
            network,
            api_path,
            "No User provided",
            expected_status=400,
        )
        _test_send_request(clc, request_two, network, api_path, expected_status=200)
