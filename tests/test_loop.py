"""Tests for the entire fuzzing loop using custom clients and APIs."""

import json
import os
import shutil
import tempfile
import textwrap
from copy import deepcopy
from json import JSONDecodeError
from pathlib import Path
from time import sleep

import pytest
import requests
from conftest import TEST_CONFIG_BASE_PATH
from docker.models.networks import Network
from requests.models import CaseInsensitiveDict
from test_client import _init_and_send

from telephuzz.config import Config
from telephuzz.evaluation.evaluator import DiffEvaluator
from telephuzz.fuzzer import TelePhuzz
from telephuzz.http_message import HTTPMethod, Request, Response
from telephuzz.invocation_data import InvocationData
from telephuzz.session.client_library import (
    OpenAPIGenPythonCLC,
    OperationIdBasedCLC,
    PythonCLC,
    SwaggerCodegenPythonCLC,
)
from telephuzz.session.session import SessionManager

# TODO move somewhere else
TESTFILES = Path(__file__).parent / "testfiles"

CLIENT_PATH = TESTFILES / "test_clients"
BASIC_CLIENT_PATH = CLIENT_PATH / "basic_client"
TEST_OAS = TESTFILES / "openapi_test_fuzzing.json"

API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_loop_config.yaml"
CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_loop_config.yaml"

CLIENT_FAULTY_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_loop_faulty_config.yaml"

LOG_PATH = Path("/tmp/logs/telephuzz")


def make_client_classes(base: type, amount: int = 3) -> list[type]:
    """Generate clients libraries for testing purposes.

    For instance, make_client_class(BasicClient)
    will generate BasicClient1, BasicClient2 and BasicClient3 classes
    with ids basicclient1, basicclient2, basicclient3.
    """
    types = []
    for i in range(amount):
        base_name = f"{base.__name__}{i + 1}"
        types.append(type(base_name, (base,), {"id": base_name.lower()}))

    return types


@pytest.fixture(autouse=True, scope="module")
def setup_loop():
    """Clear log directory."""
    if LOG_PATH.exists():
        shutil.rmtree(LOG_PATH)


class BasicClient(PythonCLC, OperationIdBasedCLC):
    id = "test-client:python"

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        allowed_args = ["name", "age", "user_id"]
        kwargs = f"api='{api_path}',"
        if invocation.query_parameters:
            kwargs += ", ".join(
                f"{k}={repr(v)}"
                for k, v in invocation.query_parameters.items()
                if k in allowed_args
            )
        if invocation.body:
            try:
                body: dict | None = dict(json.loads(invocation.body))
            except (JSONDecodeError, ValueError, TypeError):
                body = None

            if body:
                kwargs += ", ".join(
                    f"{k}={repr(v)}" for k, v in body.items() if k in allowed_args
                )

        method_name = self._get_method_name(invocation)

        content = textwrap.dedent(f"""
        from pprint import pprint
                                  
        from telephuzz_basic_client.client import {method_name}

        pprint({self._get_method_name(invocation)}({kwargs}))
        """).encode()

        return content


class BasicFaultyClient(BasicClient):
    id = "basicfaultyclient"


def test_basic_client(api: tuple[Network, str]):
    """Test that basic client works."""
    network, api_path = api
    with BasicClient(library_path=BASIC_CLIENT_PATH) as basic_client:
        assert basic_client.container is not None
        network.connect(basic_client.container)
        sleep(1)
        _init_and_send(basic_client, api_path)


def test_faulty_client(api: tuple[Network, str]):
    """Test that faulty client does not send messages correctly."""
    network, api_path = api
    with BasicFaultyClient(
        library_path=CLIENT_PATH / "basic_faulty_client"
    ) as basic_client:
        assert basic_client.container is not None
        network.connect(basic_client.container)
        sleep(1)
        with pytest.raises(AssertionError, match="Hello Faulty, you are 42"):
            _init_and_send(basic_client, api_path)


def test_session_manager_setup(monkeypatch):
    """Test setting up the session manager without db."""

    Config.API_CONFIG_PATH = API_CONFIG_PATH
    Config.CLIENT_CONFIG_PATH = CLIENT_CONFIG_PATH

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    classes = make_client_classes(BasicClient)

    with SessionManager() as session_manager:
        assert session_manager.database_type is None

        assert session_manager.mitmproxy.listen_port == 8080

        assert classes[0].id in session_manager.sessions
        assert classes[1].id in session_manager.sessions
        assert classes[2].id in session_manager.sessions
        for session in session_manager.sessions.values():
            assert session.client.container is not None
            session.client.container.reload()
            assert session.client.container.status == "running"

        assert len(session_manager.networks) == 3
        for network in session_manager.networks:
            network.reload()
            assert len(network.containers) == 3
            assert session_manager.mitmproxy.container in network.containers

        assert "docker-compose-loop.yaml" in session_manager.api_docker_compose_path

        # assert mitmproxy and target api is up by sending manual request
        session1 = session_manager.sessions[classes[0].id]

        api_url = f"http://localhost:{session_manager.mitmproxy.listen_port}"
        params = {"name": "Alice", "age": 30}
        text = requests.get(
            f"{api_url}/api{session1.id}:8000/greet",
            params=params,
        ).text
        assert "Hello Alice, you are 30 years old!" in text, (
            f"Message was not routed correctly: {text}"
        )

        # try to send a request through the send method

        request = Request(
            headers=CaseInsensitiveDict(
                {
                    "Host": "localhost:8000",
                    "User-Agent": "schemathesis/4.15.2",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                    "X-Schemathesis-TestCaseId": "3ATnwX",
                }
            ),
            body="",
            method=HTTPMethod.GET,
            path="/greet?age=0&name=",
            query_parameters={"age": "0", "name": ""},
        )

        # attempt to send with single client
        api_url = api_url.replace("localhost", "mitmproxy")
        api_url += f"/api{session1.id}:8000"
        client1 = session1.client
        invocation = InvocationData(request)
        client1.send(invocation, api_url)

        # attempt to send with session manager
        results = session_manager.send(request)
        assert len(results) == 3


def test_session_manager_faulty(monkeypatch):
    """Test setting up session manager with faulty client."""
    Config.API_CONFIG_PATH = API_CONFIG_PATH
    Config.CLIENT_CONFIG_PATH = CLIENT_FAULTY_CONFIG_PATH

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    make_client_classes(BasicClient, amount=2)

    with SessionManager() as session_manager:
        assert len(session_manager.sessions) == 3
        faulty_clients = [
            s
            for s in session_manager.sessions.values()
            if isinstance(s.client, BasicFaultyClient)
        ]
        assert len(faulty_clients) == 1

        # try to send a request and check for faulty response
        request = Request(
            headers=CaseInsensitiveDict(
                {
                    "Host": "localhost:8000",
                    "User-Agent": "schemathesis/4.15.2",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                    "X-Schemathesis-TestCaseId": "3ATnwX",
                }
            ),
            body="",
            method=HTTPMethod.GET,
            path="/greet?age=0&name=",
            query_parameters={"age": "0", "name": ""},
        )

        results = session_manager.send(request=request)
        assert any("Faulty" in repr(r) for r in results), results


def test_diff_eval(monkeypatch):
    """Test capturing and evaluating a result."""
    Config.API_CONFIG_PATH = API_CONFIG_PATH
    Config.CLIENT_CONFIG_PATH = CLIENT_CONFIG_PATH

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    make_client_classes(BasicClient)

    with SessionManager() as session_manager:
        request = Request(
            headers=CaseInsensitiveDict(
                {
                    "Host": "localhost:8000",
                    "User-Agent": "schemathesis/4.15.2",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                    "X-Schemathesis-TestCaseId": "3ATnwX",
                }
            ),
            body="",
            method=HTTPMethod.GET,
            path="/greet?age=0&name=",
            query_parameters={"age": "0", "name": ""},
        )

        # attempt to send with session manager
        results = session_manager.send(request)
        assert len(results) == 3

        evaluator = DiffEvaluator()
        evaluator.eval(results, request)

        assert len(os.listdir(LOG_PATH)) == 0


def test_mitmproxy_result_dir(monkeypatch):
    """Test obtaining a result from mitmproxy."""
    Config.API_CONFIG_PATH = API_CONFIG_PATH
    Config.CLIENT_CONFIG_PATH = CLIENT_CONFIG_PATH

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    make_client_classes(BasicClient)

    with SessionManager() as session_manager:
        api_url = f"http://localhost:{session_manager.mitmproxy.listen_port}"
        params = {"name": "Alice", "age": 30}
        assert (
            "Hello Alice, you are 30 years old!"
            in requests.get(
                f"{api_url}/api0:8000/greet",
                params=params,
            ).text
        ), "Message was not routed."

        result_dir = Path(session_manager.result_dir) / "api0"
        result_files = os.listdir(result_dir)
        assert len(result_files) == 1
        result_file = result_dir / result_files[0]
        Request.from_json(result_file)
        Response.from_json(result_file)


def test_loop_same_library(monkeypatch):
    """Test the fuzzing loop with two instances of the basic client."""
    Config.API_CONFIG_PATH = API_CONFIG_PATH
    Config.CLIENT_CONFIG_PATH = CLIENT_CONFIG_PATH

    make_client_classes(BasicClient)

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    fuzzer = TelePhuzz(TEST_OAS)
    fuzzer.start_fuzzing_session()

    assert len(os.listdir(LOG_PATH)) == 0


def test_loop_faulty_library(monkeypatch):
    """Test the fuzzing loop with two instances of the basic client."""
    Config.API_CONFIG_PATH = API_CONFIG_PATH
    Config.CLIENT_CONFIG_PATH = CLIENT_FAULTY_CONFIG_PATH

    make_client_classes(BasicClient, amount=2)

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    fuzzer = TelePhuzz(TEST_OAS)
    fuzzer.start_fuzzing_session()

    assert len(os.listdir(LOG_PATH)) > 0
    assert not any("test-client" in f for f in os.listdir(LOG_PATH))
    assert all("test-faulty-client" in f for f in os.listdir(LOG_PATH))


def test_send_petshop(monkeypatch):

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_petshop_config.yaml"

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", TESTFILES / "clients")

    make_client_classes(OpenAPIGenPythonCLC)

    request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "api_key": "^",
                "X-Schemathesis-TestCaseId": "q2GdK4",
            }
        ),
        body="",
        method=HTTPMethod.GET,
        path="/store/inventory",
        query_parameters={},
    )

    with SessionManager() as session_manager:
        results = session_manager.send(request)
        assert len(results) == 3


def test_resolve_path_params(monkeypatch):

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_petshop_config.yaml"

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", TESTFILES / "clients")

    make_client_classes(OpenAPIGenPythonCLC)

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

    with SessionManager() as session_manager:
        result = session_manager.send(request_int)
        assert len(result) == 3

        result = session_manager.send(request_str)
        assert len(result) == 3


def test_non_json_body(monkeypatch):
    """Test sending a non-json body."""

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_petshop_config.yaml"

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", TESTFILES / "clients")

    make_client_classes(OpenAPIGenPythonCLC)

    request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "fHclfr",
                "Content-Type": "application/octet-stream",
                "Content-Length": "2",
            }
        ),
        body="j\x13",
        method=HTTPMethod.POST,
        path="/pet/140737488355328/uploadImage",
        query_parameters={},
    )

    with SessionManager() as session_manager:
        result = session_manager.send(request)
        assert len(result) == 3


def test_json_body_array(monkeypatch):
    """Test sending an array as json body."""

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_petshop_config.yaml"

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", TESTFILES / "clients")

    make_client_classes(OpenAPIGenPythonCLC)

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
            },
            {
                "id": 11,
                "username": "theUser2",
                "firstName": "John",
                "lastName": "James",
                "email": "john2@email.com",
                "password": "12345",
                "phone": "12345",
                "userStatus": 1,
            },
        ]
    )

    with SessionManager() as session_manager:
        result = session_manager.send(request_empty)
        assert len(result) == 3

        result = session_manager.send(request_two)
        assert len(result) == 3
        for r in result:
            assert r.response.status == 200


def test_query_and_body(monkeypatch):
    """Test request with path variables and body."""

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_petshop_config.yaml"

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", TESTFILES / "clients")

    make_client_classes(OpenAPIGenPythonCLC)

    request_empty = Request(
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

    with SessionManager() as session_manager:
        result = session_manager.send(request_empty)
        assert len(result) == 3


def test_parse_invalid_python_json(monkeypatch):
    """Test parsing a JSON body not parseable through literal_eval."""

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_petshop_config.yaml"

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", TESTFILES / "clients")

    make_client_classes(OpenAPIGenPythonCLC)

    request_empty = Request(
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

    with SessionManager() as session_manager:
        result = session_manager.send(request_empty)
        assert len(result) == 3
        for r in result:
            assert r.response.status == 200


@pytest.mark.parametrize(
    "client_class",
    [OpenAPIGenPythonCLC, SwaggerCodegenPythonCLC],
)
def test_loop_petshop(monkeypatch, client_class: type):
    """Tets the fuzzing loop with the petshop API and six identical clients."""

    classes = make_client_classes(client_class)

    client_lib = f"pet-{client_class.__name__.lower()}"

    with tempfile.NamedTemporaryFile("w+") as client_config:
        template_config = TEST_CONFIG_BASE_PATH / "client_template_config.yaml"
        with open(template_config, "r") as template:
            template_data = template.read()

        client_config.write(
            template_data.format(
                classes[0].id,  # type: ignore
                classes[1].id,  # type: ignore
                classes[2].id,  # type: ignore
                client_lib,
            )
        )
        client_config.seek(0)

        Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
        Config.CLIENT_CONFIG_PATH = Path(client_config.name)

        monkeypatch.setattr(
            "telephuzz.session.session.CLIENT_PATH", TESTFILES / "clients"
        )

        fuzzer = TelePhuzz(TESTFILES / "processed_petshop.json")
        fuzzer.start_fuzzing_session()

        assert len(os.listdir(LOG_PATH)) == 0
