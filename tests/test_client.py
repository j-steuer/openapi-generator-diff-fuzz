"""Tests for client libraries."""

import json
import re
import tomllib
from copy import deepcopy
from pathlib import Path
from time import sleep

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
        latest_status = None
        for _ in range(50):
            try:
                latest_status = re.findall(r"<< [0-9]{3}", logs)[-1]
                break
            except Exception:
                sleep(0.1)
                logs = mitmproxy.logs().decode()
        if latest_status is None:
            raise TimeoutError("No answer received in time")
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
    [
        OpenAPIGenPythonCLC,
        SwaggerCodegenPythonCLC,
        OpenAPIPythonClientCLC,
        KiotaPythonCLC,
    ],
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

        _test_send_request(clc, request_int, network, api_path, expected_status=404)
        _test_send_request(clc, request_str, network, api_path, expected_status=404)


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

        _test_send_request(clc, request, network, api_path, expected_status=404)


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
                '{"id": 1, '
                '"name": "test", '
                '"photoUrls": ["https://example.com/photo.jpg"], '
                '"status": "available", '
                '"tags": [{"id": 2, "name": "tag"}], '
                '"isCustom": true}'
            ),
            method=HTTPMethod.POST,
            path="/pet",
            query_parameters={},
        )

        _test_send_request(clc, request, network, api_path, expected_status=200)


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
            expected_status=400,
        )
        _test_send_request(clc, request_two, network, api_path, expected_status=200)


# TODO bug with swagger codegen?
@pytest.mark.parametrize(
    "clc_class",
    [
        OpenAPIGenPythonCLC,
        OpenAPIPythonClientCLC,
        KiotaPythonCLC,
    ],
)
@pytest.mark.parametrize("api_wfd", ["swagger-petstore"], indirect=True)
def test_file_upload(clc_class, api_wfd: tuple[Network, str]):
    """Test request with file upload."""

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
                    "X-Schemathesis-TestCaseId": "PMGCFW",
                    "Content-Type": "application/octet-stream",
                    "Content-Length": "6",
                }
            ),
            body="üý»©TÎ",
            method=HTTPMethod.POST,
            path="/pet/-1714/uploadImage",
            query_parameters={"petId": -1714},
        )

        _test_send_request(
            clc,
            request,
            network,
            api_path,
            expected_status=404,
        )


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
def test_surrogate_encoding(clc_class, api_wfd: tuple[Network, str]):
    """Test encoding with surrogates."""

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
                    "X-Schemathesis-TestCaseId": "NkdOLM",
                    "Content-Type": "application/json",
                    "Content-Length": "150",
                }
            ),
            body=(
                '{"name": "(", "photoUrls": ["\\u00d3", "\\u00c7", '
                '"\\uda19\\uddbd\\u00de7\\ud815\\udd85M\\u00e6", '
                '"\\udb9f\\udf7b\\u00e0\\udb96\\udf82\\u009d\\u00b5"], "id": -24336}'
            ),
            method=HTTPMethod.PUT,
            path="/pet",
            query_parameters={},
        )

        _test_send_request(
            clc,
            request,
            network,
            api_path,
            expected_status=404,
        )


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
def test_single_explode_string(clc_class, api_wfd: tuple[Network, str]):
    """Test sending explode array with single string."""

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
                    "X-Schemathesis-TestCaseId": "W02CUe",
                }
            ),
            body="",
            method=HTTPMethod.GET,
            path="/pet/findByTags?tags=%C2%80%F0%A8%95%B3%F1%88%AC%93%C3%B6",
            query_parameters={"tags": "\x80𨕳\U00048b13ö"},
        )

        _test_send_request(
            clc,
            request,
            network,
            api_path,
            expected_status=200,
        )


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
def test_empty_octet_body(clc_class, api_wfd: tuple[Network, str]):
    """Test sending octet-stream with empty body."""

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
                    "X-Schemathesis-TestCaseId": "O4kobp",
                    "Content-Type": "application/octet-stream",
                    "Content-Length": "0",
                }
            ),
            body="",
            method=HTTPMethod.POST,
            path="/pet/1/uploadImage",
            query_parameters={"petId": 1},
        )

        _test_send_request(
            clc,
            request,
            network,
            api_path,
            expected_status=400,
        )


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
def test_enum_query_parameter(clc_class, api_wfd: tuple[Network, str]):
    """Test sending octet-stream with empty body."""

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
                    "X-Schemathesis-TestCaseId": "VzpLIV",
                }
            ),
            body="",
            method=HTTPMethod.GET,
            path="/pet/findByStatus?status=pending",
            query_parameters={"status": "pending"},
        )

        _test_send_request(
            clc,
            request,
            network,
            api_path,
            expected_status=200,
        )
