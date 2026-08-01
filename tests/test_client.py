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
    ModelCode,
    NswagCSharpCLC,
    NswagTypeScriptCLC,
    OapiGeneratorCLC,
    OpenAPIGenCsharpCLC,
    OpenAPIGenGoCLC,
    OpenAPIGenPythonCLC,
    OpenAPIGenTypeScriptCLC,
    OpenAPIPythonClientCLC,
    OpenAPIVersion,
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
        for _ in range(100):
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


def test_supported_version():
    """Test assigning the supported version."""
    assert OpenAPIVersion("2.0") == OpenAPIVersion.V_2
    assert OpenAPIVersion("3.0.1") == OpenAPIVersion.V_3_0
    assert OpenAPIVersion("3.1.0") == OpenAPIVersion.V_3_1

    with pytest.raises(ValueError):
        OpenAPIVersion("1.0")


def test_unsupported_version():
    """Test that client raises error if version is not supported."""
    # version 2.0 schema
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_languagetool_config.yaml"

    # client does not support 2.0.x
    with pytest.raises(ValueError, match="is not supported by"):
        with OpenAPIPythonClientCLC():
            pass


def test_get_method_name_opid_mixin(monkeypatch):
    """Test mixin for obtaining method names based on operation id."""
    config = get_config()

    with open("tests/testfiles/processed_petshop.json", "r") as f:
        spec = json.load(f)

    monkeypatch.setattr(config, "spec", spec)
    monkeypatch.setattr(config, "spec_str", json.dumps(spec))

    class Dummy(OperationIdBasedCLC):
        def _generate_code_models(self, invocation: InvocationData) -> ModelCode:
            return ModelCode(None, "")

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

        request_empty = deepcopy(request)
        request_empty.query_parameters.clear()

        _test_send_request(clc, request_empty, network, api_path, expected_status=400)
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
def test_request_end_with_path_variable(clc_class, api_wfd: tuple[Network, str]):
    """Test sending a request whose path ends with a path variable."""

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
                    "X-Schemathesis-TestCaseId": "k18bhp",
                    "Content-Length": "0",
                }
            ),
            body="",
            method=HTTPMethod.POST,
            path="/pet/5714?status=%C3%A3%C2%88%F2%86%AD%9A%C2%A1g%F3%95%B2%BB%0B%F2%B7%99%89%E9%BB%A5%C3%B19%0B%C3%957%C2%97n%7B",
            query_parameters={
                "status": "ã\x88\U00086b5a¡g\U000d5cbb\x0b\U000b7649黥ñ9\x0bÕ7\x97n{",
                "petId": 5714,
            },
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
@pytest.mark.parametrize("api_wfd", ["spring-batch-rest"], indirect=True)
def test_tag_module_resolve(clc_class, api_wfd: tuple[Network, str]):
    """Test resolving the module through a tag different than the base path."""

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"

    # wait for spring-batch-rest-mitmproxy to be ready
    sleep(10)

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
                    "X-Schemathesis-TestCaseId": "nEfZ5y",
                }
            ),
            body="",
            method=HTTPMethod.GET,
            path="/jobs",
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
@pytest.mark.parametrize("api_wfd", ["spring-batch-rest"], indirect=True)
def test_model_capitalization(clc_class, api_wfd: tuple[Network, str]):
    """Test capitalizing the model names correctly."""

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"

    # wait for spring-batch-rest-mitmproxy to be ready
    sleep(10)

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
                    "X-Schemathesis-TestCaseId": "lUGSOO",
                    "Content-Type": "application/json",
                    "Content-Length": "253",
                }
            ),
            body=(
                '{"\\udad6\\udefb\\u00e2\\ud812\\ude26": [], '
                '"\\u00e2\\ud806\\udd92\\ud8a4\\udff4": {"": "", '
                '"\\ud926\\uddf4\\u00a5u\\u00d6\\uda66\\ude3c\\u00ee~\\udad1'
                '\\udead\\u0086\\ud974\\udd63\\u00dbo": '
                '"a\\u0000\\u00d5D\\u0094\\u001e\\u00ddO[\\ud919\\udf63", '
                '"i": "%\\u0083"}, "__main__": [null]}'
            ),
            method=HTTPMethod.POST,
            path="/jobExecutions",
            query_parameters={},
        )

        _test_send_request(
            clc,
            request,
            network,
            api_path,
            expected_status=404,
        )


@pytest.mark.skip("TODO fix")
@pytest.mark.parametrize(
    "clc_class",
    [
        KiotaPythonCLC,
    ],
)
@pytest.mark.parametrize("api_wfd", ["spring-batch-rest"], indirect=True)
def test_p(clc_class, api_wfd: tuple[Network, str]):
    """Test capitalizing the model names correctly."""

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"

    # wait for spring-batch-rest-mitmproxy to be ready
    sleep(10)

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
                    "X-Schemathesis-TestCaseId": "fcl9z3",
                    "Content-Type": "application/json",
                    "Content-Length": "2311",
                }
            ),
            body='{"": {"\\udb72\\udc13F\\ud9a8\\udeea\\u00fb\\u0086\\ud890'
            '\\ude72\\udaef\\udc6d": [{}], "\\u0016\\u009a": [[{"\\u00eb\\u00ab'
            '\\u00f6+\\u00d0\\udad5\\udd47": true, "JI3\\u00da": true, "\\u00f1'
            '\\u00c1\\u00d6\\udbae\\udff0n\\u00f3": 15122}, [9703,'
            ' 2.617169824053021e+82, null]], {}], "\\u00c2\\u00c8\\u001b22\\u00d4":'
            ' {"\\udb2f\\udff0x\\u0012;": [-4.392955261783056e+16, "\\u0097\\u008e'
            '\\ud960\\udfe7\\u0082 \\u0014\\u00f30\\uda33\\ude17P",'
            ' 3.169622120857146e+263], "\\u00f4": 1.7976931348623157e+308, "\\b'
            '\\u00ed": [-26216, 2.2250738585e-313, -25257]}}, "\\uda83\\ude5a'
            "\\u0099\\udb8c\\udf53\\u001b\\u00cf\\ud8b8\\uded5\\u00a7\\u00e3\\u008cd"
            '\\u00f7\\udb66\\udf21\\u00e0\\u00b2": [{"+\\u0081": true, "Infinity": '
            '"\\u00d3\\bp\\udac5\\udcfa\\u0091\\u0003\\ud8c0\\udf2d\\u00ffS"}, false'
            ', {"\\u00173\\u00b6": [null, "\\udad2\\ude7d\\ud9e4\\udf98}g\\u00b8'
            '\\\\_\\u00a5\\u00c8.G", "\\ud81d\\uddd1\\b"]}], "name": "\\u00824^'
            '\\u000b5\\u0084\\u0081\\uda91\\udcbd", "\\u0287\\u01dd\\u026f\\u0250'
            " \\u0287\\u1d09s \\u0279olop \\u026fnsd\\u1d09 \\u026f\\u01dd\\u0279o"
            '\\u02e5": {}, "\\u00e1\\udbbd\\ude5a": {"": "\\u0002", "A\\udbc2\\udd09'
            '\\u00b4\\u0015\\u00db\\udac1\\udc44\\u001e\\u008f": -5e-324, "\\ud8f0'
            '\\udd82": null}, "asynchronous": true, "properties": {"\\u008e\\u008c;'
            "\\u00f8\\u00d8\\u00a2\\ud9cd\\udcd7\\u00f5\\u00f1h\\u0005;;\\u0011"
            '\\u000e\\ud95c\\udf29": {"": {"$\\u0017\\u00a8\\u00f4-\\udafe\\udf59'
            '\\ud8c9\\udde8": {"\\u00fe": [null, false, "E\\u00a6{"], "\\u0089\\udac3'
            '\\ude5cz\\u00e2\\u0083\\u0097\\u00b6\\ud8b7\\udf57\\u0080\\u00b4\\u00bf"'
            ': {"lorem \\u0644\\u0627 \\u0628\\u0633\\u0645 \\u0627\\u0644\\u0644'
            '\\u0647 ipsum \\u4f60\\u597d1234\\u4f60\\u597d": 1.1, "{": true,'
            ' "\\u00922\\uda38\\udcd8Y\\u00c2z\\ud8a4\\udeba+\\u00bc\\u00cc\\u00ed'
            '\\u00d96\\u009dK": false}, "\\u00c1\\u00b7\\u0001\\u0087": '
            '[-4432312178479263.0, false, null]}}, "\\ud9bf\\udc85\\ud9ec\\udff1JF'
            '\\u0085\\u00efq": {"\\u00a1": "k\\u00a1\\uda72\\udf7c\\u0089\\u00dc'
            '\\u00af", "\\u00f4\\udb49\\ude70Z": {"\\ud9fd\\udff5\\u00bfau'
            '\\u00e2/\\u00cdE": [], "\\u00dcj\\uda1f\\udd83\\u00f2\\u00ef":'
            ' [{"Y": false, "0\\u00f5": null}], "[?": {"": 2.617169824053021e+82,'
            ' ".exe": [], "H\\uda39\\ude71\\u0003\\u00d15": {"\\u00b6\\u00e4": false'
            ', "\\u008ao\\u00e4": -16221, "\\u0003o\\f\\u42c0\\uda9c\\udf83'
            '\\ud9f6\\udc34\\u0091": -3.3676470985717345e+169}}}, "\\u00d5": 5}'
            ', "!6": {"\\udb41\\udf0b\\u0001\\u008d\\u0085\\ud82a\\udc63\\u00c4i^'
            "\\ud9da\\udddd\\u008f\\u009fEH\\u00c2\\u0087\\uda9b\\udd30\\u0083\\udafb"
            '\\udcc4\\u00c8\\u0019\\udb5d\\ude04": false, "": 2.2898095081575256e+16,'
            ' "\\ud92e\\udd80\\"": true}}}}',
            method=HTTPMethod.POST,
            path="/jobExecutions",
            query_parameters={},
        )

        _test_send_request(
            clc,
            request,
            network,
            api_path,
            expected_status=404,
        )
