"""Tests for the entire fuzzing loop using custom clients and APIs."""

import json
import os
import shutil
import textwrap
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
from telephuzz.session.client_library import (
    OpenAPIGenPythonCLC,
    OperationIdBasedCLC,
    PythonCLC,
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


@pytest.fixture(autouse=True, scope="module")
def setup():
    """Clear log directory."""
    if LOG_PATH.exists():
        shutil.rmtree(LOG_PATH)


class BasicClient(PythonCLC, OperationIdBasedCLC):
    id = "test-client:python"

    def _get_code(self, request: Request, api_path: str) -> bytes:
        allowed_args = ["name", "age", "user_id"]
        kwargs = f"api='{api_path}',"
        if request.query_parameters:
            kwargs += ", ".join(
                f"{k}={repr(v)}"
                for k, v in request.query_parameters.items()
                if k in allowed_args
            )
        if request.body:
            try:
                body: dict | None = dict(json.loads(request.body))
            except (JSONDecodeError, ValueError, TypeError):
                body = None

            if body:
                kwargs += ", ".join(
                    f"{k}={repr(v)}" for k, v in body.items() if k in allowed_args
                )

        method_name = self._get_method_name(request)

        content = textwrap.dedent(f"""
        from pprint import pprint
                                  
        from telephuzz_basic_client.client import {method_name}

        pprint({self._get_method_name(request)}({kwargs}))
        """).encode()

        return content


class BasicClient1(BasicClient):
    id = "test-client1:python"


class BasicClient2(BasicClient):
    id = "test-client2:python"


class BasicClient3(BasicClient):
    id = "test-client3:python"


class BasicFaultyClient(BasicClient):
    id = "test-faulty-client:python"


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

    with SessionManager() as session_manager:
        assert session_manager.database_type is None

        assert session_manager.mitmproxy.listen_port == 8080

        assert BasicClient1.id in session_manager.sessions
        assert BasicClient2.id in session_manager.sessions
        assert BasicClient3.id in session_manager.sessions
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
        session1 = session_manager.sessions[BasicClient1.id]

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
        client1.send(request, api_url)

        # attempt to send with session manager
        results = session_manager.send(request)
        assert len(results) == 3


def test_session_manager_faulty(monkeypatch):
    """Test setting up session manager with faulty client."""
    Config.API_CONFIG_PATH = API_CONFIG_PATH
    Config.CLIENT_CONFIG_PATH = CLIENT_FAULTY_CONFIG_PATH

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

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

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    fuzzer = TelePhuzz(TEST_OAS)
    fuzzer.start_fuzzing_session()

    assert len(os.listdir(LOG_PATH)) == 0


def test_loop_faulty_library(monkeypatch):
    """Test the fuzzing loop with two instances of the basic client."""
    Config.API_CONFIG_PATH = API_CONFIG_PATH
    Config.CLIENT_CONFIG_PATH = CLIENT_FAULTY_CONFIG_PATH

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    fuzzer = TelePhuzz(TEST_OAS)
    fuzzer.start_fuzzing_session()

    assert len(os.listdir(LOG_PATH)) > 0
    assert not any("test-client" in f for f in os.listdir(LOG_PATH))
    assert all("test-faulty-client" in f for f in os.listdir(LOG_PATH))


def test_send_petshop(monkeypatch):
    class PetClient1(OpenAPIGenPythonCLC):
        id = "test-pet-client1:python"

    class PetClient2(OpenAPIGenPythonCLC):
        id = "test-pet-client2:python"

    class PetClient3(OpenAPIGenPythonCLC):
        id = "test-pet-client3:python"

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_petshop_config.yaml"

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", TESTFILES / "clients")

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
        session_manager.send(request)
        assert len(os.listdir(session_manager.result_dir)) == 3


def test_resolve_path_params(monkeypatch):
    class PetClient1(OpenAPIGenPythonCLC):
        id = "test-pet-client1:python"

    class PetClient2(OpenAPIGenPythonCLC):
        id = "test-pet-client2:python"

    class PetClient3(OpenAPIGenPythonCLC):
        id = "test-pet-client3:python"

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_petshop_config.yaml"

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", TESTFILES / "clients")

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
        session_manager.send(request_int)
        assert len(os.listdir(session_manager.result_dir)) == 3

        session_manager.send(request_str)
        assert len(os.listdir(session_manager.result_dir)) == 3


def test_loop_petshop(monkeypatch):
    """Tets the fuzzing loop with the petshop API and six identical clients."""

    class PetClient1(OpenAPIGenPythonCLC):
        id = "test-pet-client1:python"

    class PetClient2(OpenAPIGenPythonCLC):
        id = "test-pet-client2:python"

    class PetClient3(OpenAPIGenPythonCLC):
        id = "test-pet-client3:python"

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_petshop_config.yaml"

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", TESTFILES / "clients")

    fuzzer = TelePhuzz(TESTFILES / "processed_petshop.json")
    fuzzer.start_fuzzing_session()

    assert len(os.listdir(LOG_PATH)) == 0
