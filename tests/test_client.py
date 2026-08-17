"""Tests for client libraries."""

import datetime
import json
import re
import tomllib
from copy import deepcopy
from time import sleep

import docker
import pytest
from conftest import TEST_CONFIG_BASE_PATH
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
    PythonCLC,
    SwaggerCodegenCsharpCLC,
    SwaggerCodegenPythonCLC,
    SwaggerCodegenTypeScriptCLC,
    SwaggerTsAPICLC,
)

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
        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_languagetool_config.yaml"

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
            body="",
            method=HTTPMethod.DELETE,
            path="/user/123",
            query_parameters={},
        )

        assert mixin._get_method_name(InvocationData(request)) == generate_operation_id(
            HTTPMethod.DELETE.value, "/user/{username}"
        )

    def test_version_overwrite(self) -> None:
        """Spec version should be overwritten for clients that use it for generation."""
        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
        with OpenAPIPythonClientCLC() as _:
            clients_dir = BASE_PATH / "clients"
            client_dir = next(d for d in clients_dir.iterdir() if d.is_dir())
            with open(client_dir / "pyproject.toml", "rb") as f:
                data = tomllib.load(f)

            assert "SNAPSHOT" not in data["tool"]["poetry"]["version"]

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


@pytest.mark.usefixtures("petshop")
class TestPetshop:
    """Tests that use the petshop API/CLC."""

    def test_version_overwrite(self) -> None:
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
    def test_resolve_path_params(self, clc_class, petshop: tuple[Network, str]):

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

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
    def test_parse_invalid_python_json(self, clc_class, petshop: tuple[Network, str]):
        """Test parsing a JSON body not parseable through literal_eval."""

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

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
    def test_query_and_body(self, clc_class, petshop: tuple[Network, str]):
        """Test request with path variables and body."""

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

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
    def test_json_body_array(self, clc_class, petshop: tuple[Network, str]):
        """Test request with path variables and body."""

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

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
    def test_file_upload(self, clc_class, petshop: tuple[Network, str]):
        """Test request with file upload."""

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

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
    def test_surrogate_encoding(self, clc_class, petshop: tuple[Network, str]):
        """Test encoding with surrogates."""

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

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
                    '{"name": "(", "photoUrls": ["\\u00d3", "\\u00c7", '
                    '"\\uda19\\uddbd\\u00de7\\ud815\\udd85M\\u00e6", '
                    '"\\udb9f\\udf7b\\u00e0\\udb96\\udf82\\u009d\\u00b5"],'
                    ' "id": -24336}'
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
    def test_single_explode_string(self, clc_class, petshop: tuple[Network, str]):
        """Test sending explode array with single string."""

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

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
    def test_empty_octet_body(self, clc_class, petshop: tuple[Network, str]):
        """Test sending octet-stream with empty body."""

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

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
    def test_enum_query_parameter(self, clc_class, petshop: tuple[Network, str]):
        """Test sending octet-stream with empty body."""

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

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
                body="",
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

    @pytest.mark.parametrize(
        "clc_class",
        [
            OpenAPIGenPythonCLC,
            SwaggerCodegenPythonCLC,
            OpenAPIPythonClientCLC,
            KiotaPythonCLC,
        ],
    )
    def test_request_end_with_path_variable(
        self, clc_class, petshop: tuple[Network, str]
    ):
        """Test sending a request whose path ends with a path variable."""

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

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
                body="",
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

    @pytest.mark.parametrize(
        "clc_class",
        [
            OpenAPIGenPythonCLC,
            SwaggerCodegenPythonCLC,
            OpenAPIPythonClientCLC,
            KiotaPythonCLC,
        ],
    )
    def test_p(self, clc_class, petshop: tuple[Network, str]):
        """Test sending a request whose path ends with a path variable."""

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

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
                        "X-Schemathesis-TestCaseId": "2JIFHY",
                        "Content-Length": "0",
                    }
                ),
                body="",
                method=HTTPMethod.POST,
                path="/store/order",
                query_parameters={},
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


@pytest.mark.usefixtures("spring_batch")
class TestSpringBatch:
    """Tests that use the spring-batch-rest API."""

    @pytest.mark.parametrize(
        "clc_class",
        [
            OpenAPIGenPythonCLC,
            SwaggerCodegenPythonCLC,
            OpenAPIPythonClientCLC,
            KiotaPythonCLC,
        ],
    )
    def test_tag_module_resolve(self, clc_class, spring_batch: tuple[Network, str]):
        """Test resolving the module through a tag different than the base path."""

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"

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
    def test_model_capitalization(self, clc_class, spring_batch: tuple[Network, str]):
        """Test capitalizing the model names correctly."""

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"

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


@pytest.fixture(scope="class")
def http_patch_spring():
    network, api_name = api_wfd("http-patch-spring")
    yield network, api_name
    api_down(network, "http-patch-spring")


@pytest.mark.usefixtures("http_patch_spring")
class TestPatchSpring:
    @pytest.mark.parametrize(
        "clc_class",
        [
            OpenAPIGenPythonCLC,
            SwaggerCodegenPythonCLC,
            OpenAPIPythonClientCLC,
            KiotaPythonCLC,
        ],
    )
    def test_alternate_json_with_pure_body(
        self, clc_class, http_patch_spring: tuple[Network, str]
    ):
        """Test sending with alternate JSON type."""

        Config.API_CONFIG_PATH = (
            TEST_CONFIG_BASE_PATH / "api_http_patch_spring_config.yaml"
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
                    '{"\\udbba\\udd85fW\\u00cc\\u00e1x\\u0014[q'
                    "\\ud8da\\ude98\\ud800\\udeab\\ud8ad\\udd22kTn"
                    '\\u00cb:\\udaea\\udf4d": {}, ",\\u0017\\u00a2'
                    '\\u00d0": {}, "\\u00a0\\ud8e2\\udd5c5\\u00fd'
                    '\\uda7f\\ude00\\u00ae\\u00bb\\u00a4\\u0017\\u00de": '
                    '{"\\u0080\\u00a1\\u00c0i\\ud8d3\\udf05w\\u00f5'
                    '\\u00ca\\u00cde\\u00ea\\u00ee\\ud8e1\\udc23": 0}, '
                    '"+\\u00b9q\\u00de\\u00be\\u00d3 \\u00c0": [], '
                    '"": 0}'
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
