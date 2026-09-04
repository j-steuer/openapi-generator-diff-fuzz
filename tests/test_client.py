"""Tests for client libraries."""

import datetime
import json
import re
from copy import deepcopy
from time import sleep

import docker
import pytest
from conftest import TEST_CONFIG_2_0_BASE_PATH, TEST_CONFIG_3_0_BASE_PATH
from docker.models.networks import Network
from requests.models import CaseInsensitiveDict

from telephuzz.config import Config, get_config
from telephuzz.constants import BASE_PATH
from telephuzz.docker_helpers import compose_down, compose_up
from telephuzz.http_message import HTTPMethod, Request
from telephuzz.invocation_data import InvocationData
from telephuzz.operation_ids import generate_operation_id
from telephuzz.session.client_library import (
    ClientLibraryContainer,
    CsharpCLC,
    KiotaPythonCLC,
    ModelCode,
    OpenAPIGenCsharpCLC,
    OpenAPIGenPythonCLC,
    OpenAPIPythonClientCLC,
    OpenAPIVersion,
    OperationIdBasedCLC,
    PythonCLC,
    SwaggerCodegenPythonCLC,
)


def api_wfd(api_name: str) -> tuple[Network, str]:
    """Run a WFD api."""
    client = docker.from_env()
    name = "api_wfd_fixture"
    network = client.networks.create(name)

    compose_base_path = BASE_PATH / "wfd/dockerfiles"
    compose_path = compose_base_path / f"{api_name}.yaml"
    compose_up(compose_path=compose_path, project=name)

    api_containers = client.containers.list(
        all=True,
        filters={"label": f"com.docker.compose.project={name}"},
    )
    for api_container in api_containers:
        if api_container.name and api_name in api_container.name:
            network.connect(api_container, aliases=[api_name])
        elif "mitmproxy" in str(api_container.name):
            network.connect(api_container, aliases=["mitmproxy"])
        else:
            network.connect(api_container)

    return network, "http://mitmproxy:8080/api/v3"


def api_down(network: Network, api_name: str) -> None:
    """Tear down wfd API."""
    compose_base_path = BASE_PATH / "wfd/dockerfiles"
    compose_path = compose_base_path / f"{api_name}.yaml"
    compose_down(compose_path=compose_path, project="api_wfd_fixture")
    network.remove()


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

    timestamp = datetime.datetime.now(datetime.timezone.utc)

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
        logs = mitmproxy.logs(since=timestamp).decode()
        latest_status = None
        for _ in range(100):
            try:
                latest_status = re.findall(r"<< [0-9]{3}", logs)[-1]
                break
            except Exception:
                sleep(0.1)
                logs = mitmproxy.logs(since=timestamp).decode()
        if latest_status is None:
            raise TimeoutError("No answer received in time")
        assert f"<< {expected_status}" == latest_status

    network.disconnect(clc.container)


class TestGeneral:
    """Tests that do not require an API/CLC."""

    def test_from_id(self):
        """Test obtaining a class based on id."""
        client_type = ClientLibraryContainer.from_id("openapi-generator:python")
        assert client_type == OpenAPIGenPythonCLC

    def test_supported_version(self):
        """Test assigning the supported version."""
        assert OpenAPIVersion("2.0") == OpenAPIVersion.V_2
        assert OpenAPIVersion("3.0.1") == OpenAPIVersion.V_3_0
        assert OpenAPIVersion("3.1.0") == OpenAPIVersion.V_3_1

        with pytest.raises(ValueError):
            OpenAPIVersion("1.0")

    def test_unsupported_version(self):
        """Test that client raises error if version is not supported."""
        # version 2.0 schema
        Config.API_CONFIG_PATH = (
            TEST_CONFIG_2_0_BASE_PATH / "api_languagetool_config.yaml"
        )

        # client does not support 2.0.x
        with pytest.raises(ValueError, match="is not supported by"):
            with OpenAPIPythonClientCLC():
                pass

    def test_get_method_name_opid_mixin(self, monkeypatch):
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
            body=b"",
            method=HTTPMethod.DELETE,
            path="/user/123",
            query_parameters={},
        )

        assert mixin._get_method_name(InvocationData(request)) == generate_operation_id(
            HTTPMethod.DELETE.value, "/user/{username}"
        )

    def test_variable_case(self, monkeypatch) -> None:
        """Test that variable cases are applied correctly."""

        def _test_case(clc_class, query, expected):
            monkeypatch.setattr(clc_class, "__abstractmethods__", set())
            invocation = InvocationData.__new__(InvocationData)
            invocation.query_parameters = query
            invocation.operation_id = "get_test"
            invocation.query_parameters_without_path_vars = {}
            invocation.arg_types = {}

            clc = clc_class.__new__(clc_class)
            cased_parameters = clc._apply_case_to_invocation(invocation)
            assert cased_parameters.query_parameters == expected

        # Python should apply snake case
        query = {"TestId": 1, "birthDate": "2000-01-01"}
        _test_case(PythonCLC, query, {"test_id": 1, "birth_date": "2000-01-01"})

        # C# should apply camel case
        query = {"test_id": 1, "birthDate": "2000-01-01"}
        _test_case(CsharpCLC, query, {"testId": 1, "birthDate": "2000-01-01"})


@pytest.fixture(scope="class")
def petshop():
    network, api_path = api_wfd("swagger-petstore")
    yield network, api_path
    api_down(network, "swagger-petstore")


@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(SwaggerCodegenPythonCLC, id="swagger-codegen-python"),
        pytest.param(OpenAPIPythonClientCLC, id="openapi-python-client"),
        pytest.param(KiotaPythonCLC, id="kiota-python"),
        pytest.param(OpenAPIGenCsharpCLC, id="openapi-gen-csharp"),
    ],
)
@pytest.mark.usefixtures("petshop")
class TestPetshop:
    """Tests that use the petshop API/CLC."""

    def test_resolve_path_params(self, clc_class, petshop: tuple[Network, str]):

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_swagger_petstore_config.yaml"
        )

        network, api_path = petshop
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
                body=b"",
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
                body=b"",
                method=HTTPMethod.GET,
                path="/user/105",
                query_parameters={},
            )

            _test_send_request(clc, request_int, network, api_path, expected_status=404)
            _test_send_request(clc, request_str, network, api_path, expected_status=404)

    def test_parse_invalid_python_json(self, clc_class, petshop: tuple[Network, str]):
        """Test parsing a JSON body not parseable through literal_eval."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_swagger_petstore_config.yaml"
        )

        network, api_path = petshop
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
                    b'{"id": 1, '
                    b'"name": "test", '
                    b'"photoUrls": ["https://example.com/photo.jpg"], '
                    b'"status": "available", '
                    b'"tags": [{"id": 2, "name": "tag"}], '
                    b'"isCustom": true}'
                ),
                method=HTTPMethod.POST,
                path="/pet",
                query_parameters={},
            )

            _test_send_request(clc, request, network, api_path, expected_status=200)

    def test_query_and_body(self, clc_class, petshop: tuple[Network, str]):
        """Test request with path variables and body."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_swagger_petstore_config.yaml"
        )

        network, api_path = petshop
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
                body=b"{}",
                method=HTTPMethod.PUT,
                path="/user/%C2%A6g%F4%84%82%90%C2%BB%C2%8F%C2%80%0Cr",
                query_parameters={},
            )

            _test_send_request(clc, request, network, api_path, expected_status=404)

    def test_json_body_array(self, clc_class, petshop: tuple[Network, str]):
        """Test request with path variables and body."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_swagger_petstore_config.yaml"
        )

        network, api_path = petshop
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
                body=b"[]",
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
            ).encode()

            _test_send_request(
                clc,
                request_empty,
                network,
                api_path,
                expected_status=400,
            )
            _test_send_request(clc, request_two, network, api_path, expected_status=200)

    def test_file_upload(self, clc_class, petshop: tuple[Network, str]):
        """Test request with file upload."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_swagger_petstore_config.yaml"
        )

        network, api_path = petshop
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
                body=b"a",
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

    def test_surrogate_encoding(self, clc_class, petshop: tuple[Network, str]):
        """Test encoding with surrogates."""

        if clc_class is OpenAPIGenCsharpCLC:
            pytest.xfail("OpenAPI Generator C# does not support optional enum values")

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_swagger_petstore_config.yaml"
        )

        network, api_path = petshop
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
                    b'{"name": "(", "photoUrls": ["\\u00d3", "\\u00c7", '
                    b'"\\uda19\\uddbd\\u00de7\\ud815\\udd85M\\u00e6", '
                    b'"\\udb9f\\udf7b\\u00e0\\udb96\\udf82\\u009d\\u00b5"],'
                    b' "id": -24336}'
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

    def test_single_explode_string(self, clc_class, petshop: tuple[Network, str]):
        """Test sending explode array with single string."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_swagger_petstore_config.yaml"
        )

        network, api_path = petshop
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
                body=b"",
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

    def test_empty_octet_body(self, clc_class, petshop: tuple[Network, str]):
        """Test sending octet-stream with empty body."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_swagger_petstore_config.yaml"
        )

        network, api_path = petshop
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
                body=b"",
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

    def test_enum_query_parameter(self, clc_class, petshop: tuple[Network, str]):
        """Test sending octet-stream with empty body."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_swagger_petstore_config.yaml"
        )

        network, api_path = petshop
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
                body=b"",
                method=HTTPMethod.GET,
                path="/pet/findByStatus?status=pending",
                query_parameters={"status": "pending"},
            )

            request_empty = deepcopy(request)
            request_empty.query_parameters.clear()

            _test_send_request(
                clc,
                request_empty,
                network,
                api_path,
                expected_status=400,
            )
            _test_send_request(clc, request, network, api_path, expected_status=200)

    def test_request_end_with_path_variable(
        self, clc_class, petshop: tuple[Network, str]
    ):
        """Test sending a request whose path ends with a path variable."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_swagger_petstore_config.yaml"
        )

        network, api_path = petshop
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
                body=b"",
                method=HTTPMethod.POST,
                path="/pet/5714?status=%C3%A3%C2%88%F2%86%AD%9A%C2%A1g%F3%95%B2%BB%0B%F2%B7%99%89%E9%BB%A5%C3%B19%0B%C3%957%C2%97n%7B",
                query_parameters={
                    "status": "ã\x88\U00086b5a¡g\U000d5cbb\x0b\U000b7649黥ñ9\x0bÕ7",
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


@pytest.fixture(scope="class")
def spring_batch():
    network, api_name = api_wfd("spring-batch-rest")
    yield network, api_name
    api_down(network, "spring-batch-rest")


@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(SwaggerCodegenPythonCLC, id="swagger-codegen.python"),
        pytest.param(OpenAPIPythonClientCLC, id="openapi-python-client"),
        pytest.param(KiotaPythonCLC, id="kiota-python"),
        pytest.param(OpenAPIGenCsharpCLC, id="openapi-gen-csharp"),
    ],
)
@pytest.mark.usefixtures("spring_batch")
class TestSpringBatch:
    """Tests that use the spring-batch-rest API."""

    def test_tag_module_resolve(self, clc_class, spring_batch: tuple[Network, str]):
        """Test resolving the module through a tag different than the base path."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_spring_batch_rest_config.yaml"
        )

        # wait for spring-batch-rest-mitmproxy to be ready
        sleep(10)

        network, api_path = spring_batch
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
                body=b"",
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

    def test_model_capitalization(self, clc_class, spring_batch: tuple[Network, str]):
        """Test capitalizing the model names correctly."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_spring_batch_rest_config.yaml"
        )

        # wait for spring-batch-rest-mitmproxy to be ready
        sleep(10)

        network, api_path = spring_batch
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
                    b'{"\\udad6\\udefb\\u00e2\\ud812\\ude26": [], '
                    b'"\\u00e2\\ud806\\udd92\\ud8a4\\udff4": {"": "", '
                    b'"\\ud926\\uddf4\\u00a5u\\u00d6\\uda66\\ude3c\\u00ee~\\udad1'
                    b'\\udead\\u0086\\ud974\\udd63\\u00dbo": '
                    b'"a\\u0000\\u00d5D\\u0094\\u001e\\u00ddO[\\ud919\\udf63", '
                    b'"i": "%\\u0083"}, "__main__": [null]}'
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


@pytest.fixture(scope="class")
def http_patch_spring():
    network, api_name = api_wfd("http-patch-spring")
    yield network, api_name
    api_down(network, "http-patch-spring")


@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(SwaggerCodegenPythonCLC, id="swagger-codegen.python"),
        pytest.param(OpenAPIPythonClientCLC, id="openapi-python-client"),
        pytest.param(KiotaPythonCLC, id="kiota-python"),
        pytest.param(OpenAPIGenCsharpCLC, id="openapi-gen-csharp"),
    ],
)
@pytest.mark.usefixtures("http_patch_spring")
class TestPatchSpring:
    def test_alternate_json_with_pure_body(
        self, clc_class, http_patch_spring: tuple[Network, str]
    ):
        """Test sending with alternate JSON type."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_http_patch_spring_config.yaml"
        )

        sleep(5)

        network, api_path = http_patch_spring
        with clc_class() as clc:
            request = Request(
                headers=CaseInsensitiveDict(
                    {
                        "Host": "localhost:8000",
                        "User-Agent": "schemathesis/4.15.2",
                        "Accept-Encoding": "gzip, deflate, br",
                        "Accept": "*/*",
                        "Connection": "keep-alive",
                        "X-Schemathesis-TestCaseId": "Dd1aWs",
                        "Content-Type": "application/merge-patch+json",
                        "Content-Length": "331",
                    }
                ),
                body=(
                    b'{"\\udbba\\udd85fW\\u00cc\\u00e1x\\u0014[q'
                    b"\\ud8da\\ude98\\ud800\\udeab\\ud8ad\\udd22kTn"
                    b'\\u00cb:\\udaea\\udf4d": {}, ",\\u0017\\u00a2'
                    b'\\u00d0": {}, "\\u00a0\\ud8e2\\udd5c5\\u00fd'
                    b'\\uda7f\\ude00\\u00ae\\u00bb\\u00a4\\u0017\\u00de": '
                    b'{"\\u0080\\u00a1\\u00c0i\\ud8d3\\udf05w\\u00f5'
                    b'\\u00ca\\u00cde\\u00ea\\u00ee\\ud8e1\\udc23": 0}, '
                    b'"+\\u00b9q\\u00de\\u00be\\u00d3 \\u00c0": [], '
                    b'"": 0}'
                ),
                method=HTTPMethod.PATCH,
                path="/contacts/70",
                query_parameters={"id": 70},
            )

            _test_send_request(
                clc,
                request,
                network,
                api_path,
                expected_status=404,
            )


@pytest.fixture(scope="class")
def genome_nexus():
    network, api_name = api_wfd("genome-nexus")
    yield network, api_name
    api_down(network, "genome-nexus")


@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(OpenAPIGenCsharpCLC, id="openapi-gen-csharp"),
    ],
)
@pytest.mark.usefixtures("genome_nexus")
class TestGenomeNexus:
    def test_body_name(self, clc_class):
        """Client should apply body name in swagger 2.0."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_2_0_BASE_PATH / "api_genome_nexus_config.yaml"
        )

        with clc_class() as clc:
            request = Request(
                headers=CaseInsensitiveDict({"content-type": "application/json"}),
                body=b"[]",
                method=HTTPMethod.POST,
                path="/annotation",
                query_parameters={},
            )

            code = clc._get_code(InvocationData(request), "test")
            assert b"variants=" in code
            assert b"body=" not in code


@pytest.fixture(scope="class")
def catwatch():
    network, api_name = api_wfd("catwatch")
    yield network, api_name
    api_down(network, "catwatch")


@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(OpenAPIGenCsharpCLC, id="openapi-gen-csharp"),
        pytest.param(KiotaPythonCLC, id="kiota-python"),
    ],
)
@pytest.mark.usefixtures("catwatch")
class TestCatwatch:
    def test_dot_case(self, clc_class, catwatch: tuple[Network, str]):
        """Test sending a request with a dot variable."""

        Config.API_CONFIG_PATH = TEST_CONFIG_2_0_BASE_PATH / "api_catwatch_config.yaml"

        sleep(10)

        network, api_path = catwatch
        with clc_class() as clc:
            request = Request(
                headers=CaseInsensitiveDict(),
                body=b"",
                method=HTTPMethod.GET,
                path="/health.json",
                query_parameters={},
            )

            _test_send_request(
                clc,
                request,
                network,
                api_path,
                expected_status=404,
            )


@pytest.fixture(scope="class")
def cwa_verification():
    network, api_name = api_wfd("cwa-verification")
    yield network, api_name
    api_down(network, "cwa-verification")


@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(OpenAPIPythonClientCLC, id="openapi-python-client"),
        pytest.param(OpenAPIGenCsharpCLC, id="openapi-gen-csharp"),
        pytest.param(KiotaPythonCLC, id="kiota-python"),
    ],
)
@pytest.mark.usefixtures("cwa_verification")
class TestCwaVerification:
    def test_dash_case(self, clc_class, cwa_verification: tuple[Network, str]):
        """Test sending a request with a dash variable."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_cwa_verification_config.yaml"
        )

        sleep(15)

        network, api_path = cwa_verification
        with clc_class() as clc:
            request = Request(
                headers=CaseInsensitiveDict({"content-type": "application/json"}),
                body=b'{"registrationToken": "00000000-0000-4000-8000-000000000000"}',
                method=HTTPMethod.POST,
                path="/version/v1/tan",
                query_parameters={},
            )

            _test_send_request(
                clc,
                request,
                network,
                api_path,
                expected_status=302,
            )


@pytest.fixture(scope="class")
def person_controller():
    network, api_name = api_wfd("person-controller")
    yield network, api_name
    api_down(network, "person-controller")


@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(KiotaPythonCLC, id="kiota-python"),
    ],
)
@pytest.mark.usefixtures("person_controller")
class TestPersonController:
    def test_resolve_schema_name_with_uppercase_sequence(
        self, clc_class, person_controller: tuple[Network, str]
    ):

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_3_0_BASE_PATH / "api_person_controller_config.yaml"
        )

        sleep(10)

        network, api_path = person_controller
        with clc_class() as clc:
            request = Request(
                headers=CaseInsensitiveDict({"content-type": "application/json"}),
                body=b"[{}, {}]",
                method=HTTPMethod.POST,
                path="/api/persons",
                query_parameters={},
            )

            _test_send_request(
                clc,
                request,
                network,
                api_path,
                expected_status=404,
            )


@pytest.fixture(scope="class")
def user_management():
    network, api_name = api_wfd("user-management")
    yield network, api_name
    api_down(network, "user-management")


@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(KiotaPythonCLC, id="kiota-python"),
    ],
)
@pytest.mark.usefixtures("user_management")
class TestUserManagement:
    def test_uppercase_sequence(self, clc_class, user_management: tuple[Network, str]):

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_2_0_BASE_PATH / "api_user_management_config.yaml"
        )

        sleep(10)

        network, api_path = user_management
        with clc_class() as clc:
            request = Request(
                headers=CaseInsensitiveDict({"content-type": "application/json"}),
                body=b"{}",
                method=HTTPMethod.POST,
                path="/login",
                query_parameters={},
            )

            _test_send_request(
                clc,
                request,
                network,
                api_path,
                expected_status=404,
            )


@pytest.fixture(scope="class")
def gestaohospital():
    network, api_name = api_wfd("gestaohospital")
    yield network, api_name
    api_down(network, "gestaohospital")


# TODO fix
@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(KiotaPythonCLC, id="kiota-python"),
    ],
)
@pytest.mark.usefixtures("gestaohospital")
class TestGestaohospital:
    def test_schema_body_name(self, clc_class, gestaohospital: tuple[Network, str]):
        """Parameter name should be used over schema name."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_2_0_BASE_PATH / "api_gestaohospital_config.yaml"
        )

        sleep(10)

        network, api_path = gestaohospital
        with clc_class() as clc:
            request = Request(
                headers=CaseInsensitiveDict({"content-type": "application/json"}),
                body=(
                    b'{"latitude": "\\u001f\\u0081\\u0002\\uda9f\\ude84\\u007fl'
                    b"\\udb11\\ude2b\\u00e2\\ud8d6\\udef3\\u00a3AE'\\u000b\\u00baI"
                    b"\\u0011\\ud906\\ude11*\\u00b9\\u00e1Vu\\u00de\\udbc6\\udcb5"
                    b"\\u00e8\\u00de<^y\\u0099\\u001e\\u00e9\\u00df\\u0010\\u0003"
                    b'\\uda88\\udd74\\u0083", "id": "$", "address": "`\\u00a7",'
                    b' "name": "\\u00d3", "availableBeds": -426}'
                ),
                method=HTTPMethod.POST,
                path="/v1/hospitais/",
                query_parameters={},
            )

            _test_send_request(
                clc,
                request,
                network,
                api_path,
                expected_status=404,
            )


@pytest.fixture(scope="class")
def rest_news():
    network, api_name = api_wfd("rest-news")
    yield network, api_name
    api_down(network, "rest-news")


# TODO fix
@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(KiotaPythonCLC, id="kiota-python"),
    ],
)
@pytest.mark.usefixtures("rest_news")
class TestRestNews:
    def test_in_body(self, clc_class, rest_news: tuple[Network, str]):
        """Client should properly detect "in": "body"."""

        Config.API_CONFIG_PATH = TEST_CONFIG_2_0_BASE_PATH / "api_rest_news_config.yaml"

        sleep(10)

        network, api_path = rest_news
        with clc_class() as clc:
            request = Request(
                headers=CaseInsensitiveDict(),
                body=b"",
                method=HTTPMethod.PUT,
                path="/news/13042/text",
                query_parameters={},
            )

            _test_send_request(
                clc,
                request,
                network,
                api_path,
                expected_status=404,
            )


@pytest.fixture(scope="class")
def rest_scs():
    network, api_name = api_wfd("rest-scs")
    yield network, api_name
    api_down(network, "rest-scs")


@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(KiotaPythonCLC, id="kiota-python"),
    ],
)
@pytest.mark.usefixtures("rest_scs")
# TODO fix
class TestRestScs:
    def test_single_char_sequences(self, clc_class, rest_scs: tuple[Network, str]):
        """Test sending to an endpoint with single char sequences in operation id."""

        Config.API_CONFIG_PATH = TEST_CONFIG_2_0_BASE_PATH / "api_rest_scs_config.yaml"

        sleep(10)

        network, api_path = rest_scs
        with clc_class() as clc:
            request = Request(
                headers=CaseInsensitiveDict(),
                body=b"",
                method=HTTPMethod.GET,
                path="/api/notypevar/1895/%C3%96L%0A",
                query_parameters={},
            )

            _test_send_request(
                clc,
                request,
                network,
                api_path,
                expected_status=404,
            )


@pytest.fixture(scope="class")
def session_service():
    network, api_name = api_wfd("session-service")
    yield network, api_name
    api_down(network, "session-service")


@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(KiotaPythonCLC, id="kiota-python"),
    ],
)
@pytest.mark.usefixtures("session_service")
# TODO fix
class TestSessionService:
    def test_field(self, clc_class, session_service: tuple[Network, str]):
        """Field parameter name is sanitized for some clients."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_2_0_BASE_PATH / "api_session_service_config.yaml"
        )

        sleep(10)

        network, api_path = session_service
        with clc_class() as clc:
            request = Request(
                headers=CaseInsensitiveDict(),
                body=b"",
                method=HTTPMethod.GET,
                path=(
                    "/api/sessions/k%C2%A8%C3%8C%C2%B2%C2%B7%C2%BB/"
                    "virtual_study/query?value=&field=.exe"
                ),
                query_parameters={"value": "", "field": ".exe"},
            )

            _test_send_request(
                clc,
                request,
                network,
                api_path,
                expected_status=404,
            )


@pytest.fixture(scope="class")
def youtube_mock():
    network, api_name = api_wfd("youtube-mock")
    yield network, api_name
    api_down(network, "youtube-mock")


@pytest.mark.parametrize(
    "clc_class",
    [
        pytest.param(OpenAPIGenPythonCLC, id="openapi-gen-python"),
        pytest.param(KiotaPythonCLC, id="kiota-python"),
    ],
)
@pytest.mark.usefixtures("youtube_mock")
# TODO fix
class TestYoutubeMock:
    def test_boolean(self, clc_class, youtube_mock: tuple[Network, str]):
        """Test field with boolean."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_2_0_BASE_PATH / "api_youtube_mock_config.yaml"
        )

        sleep(10)

        network, api_path = youtube_mock
        with clc_class() as clc:
            request = Request(
                headers=CaseInsensitiveDict(),
                body=b"",
                method=HTTPMethod.GET,
                path=(
                    "/search?relatedToVideoId=%3F%C3%A1%C2%8Bc%0A%7B%C2%A5%"
                    "C2%AE%C2%BC%F0%A2%82%AA%C3%AFi&forMine=false&type=%C2%93%"
                    "C2%A3%F1%BC%B2%98%C3%B2e%C3%A2u%C3%A9%23%1Ed%C2%BE%C3%A8%"
                    "C2%AC%C2%A7%C2%8A%14%C3%94%F1%BB%A1%BF%C2%95%05%C3%8A%F1%8B"
                    "%9E%B7s%F0%A3%B1%BE%C2%AFv%7B%C3%B5S0%C2%90%F1%80%9E%88%164v"
                    "%F3%9B%AA%83%C2%A4%C3%93%C3%93%C3%93%F1%A1%9A%A4_i%C2%B0%F0%B5"
                    "%B8%85%F1%BF%AB%9F%F1%8A%A9%83f%C3%B4%C2%A2&videoEmbeddable="
                    "any&videoLicense=youtube&videoDuration=long&part=snippet&topicId"
                    "=%1B%C3%BC%1D%07%F1%87%A5%B8i%F3%8D%AE%88%C3%A9&videoDefinition="
                    "high&location=%E4%B3%A2%60%C3%BB%F1%AF%B3%95-%15MQ%26&video"
                    "Caption=any&onBehalfOfContentOwner=&videoSyndicated=any"
                ),
                query_parameters={
                    "relatedToVideoId": "?á\x8bc\n{¥®¼𢂪ïi",
                    "forMine": "false",
                    "type": (
                        "\x93£\U0007cc98òeâué#\x1ed¾è¬§\x8a\x14Ô\U0007b87f\x95\x05Ê"
                        "\U0004b7b7s𣱾¯v{õS0\x90\U00040788\x164v\U000dba83¤ÓÓÓ"
                        "\U000616a4_i°\U00035e05\U0007fadf\U0004aa43fô¢"
                    ),
                    "videoEmbeddable": "any",
                    "videoLicense": "youtube",
                    "videoDuration": "long",
                    "part": "snippet",
                    "topicId": "\x1bü\x1d\x07\U00047978i\U000cdb88é",
                    "videoDefinition": "high",
                    "location": "䳢`û\U0006fcd5-\x15MQ&",
                    "videoCaption": "any",
                    "onBehalfOfContentOwner": "",
                    "videoSyndicated": "any",
                },
            )

            _test_send_request(
                clc,
                request,
                network,
                api_path,
                expected_status=404,
            )
