"""Tests for the entire fuzzing loop using custom clients and APIs."""

import json
import os
import shutil
import textwrap
from pathlib import Path

import pytest
import requests
from requests.models import CaseInsensitiveDict
from test_client import _init_and_send

from telephuzz.config import Config
from telephuzz.evaluation.evaluator import DiffEvaluator
from telephuzz.fuzzer import TelePhuzz
from telephuzz.http_message import HTTPMethod, Request, Response
from telephuzz.session.client_library import OperationIdBasedCLC, PythonCLC
from telephuzz.session.session import SessionManager

# TODO move somewhere else
TESTFILES = Path(__file__).parent / "testfiles"

CLIENT_PATH = TESTFILES / "test_clients"
BASIC_CLIENT_PATH = CLIENT_PATH / "basic_client"
TEST_OAS = TESTFILES / "openapi_test_fuzzing.json"
CONFIG_PATH = TESTFILES / "loop_config.yaml"

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
            except Exception:
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


def test_basic_client(api):
    """Test that basic client works."""
    with BasicClient(library_path=BASIC_CLIENT_PATH) as basic_client:
        _init_and_send(basic_client, api)


def test_session_manager_setup(monkeypatch):
    """Test setting up the session manager without db."""

    Config.CONFIG_PATH = CONFIG_PATH

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    with SessionManager() as session_manager:
        assert session_manager.database_type is None

        assert session_manager.mitmproxy.listen_port == 8080

        assert len(session_manager.sessions) == 3
        assert BasicClient1.id in session_manager.sessions
        assert BasicClient2.id in session_manager.sessions
        assert BasicClient3.id in session_manager.sessions

        assert "docker-compose-loop.yaml" in session_manager.api_docker_compose_path

        # assert mitmproxy and target api is up by sending manual request
        api_port = session_manager.sessions[BasicClient1.id].api.port
        api_url = f"http://localhost:{session_manager.mitmproxy.listen_port}"
        params = {"name": "Alice", "age": 30}
        assert (
            "Hello Alice, you are 30 years old!"
            in requests.get(
                f"{api_url}/localhost:{api_port}/greet",
                params=params,
            ).text
        ), "Message was not routed."

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
        client1 = session_manager.sessions[BasicClient1.id].client
        api_url = api_url.replace("localhost", "host.docker.internal")
        client1.send(request, api_url)

        # attempt to send with session manager
        request.headers["X-TEST"] = "1"
        results = session_manager.send(request)
        assert len(results) == 3

        for result in results:
            assert "X-TEST" in result.request.headers


def test_diff_eval(monkeypatch):
    """Test capturing and evaluating a result."""
    Config.CONFIG_PATH = CONFIG_PATH

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


def test_warmup(monkeypatch):
    """Try sending requests with a session."""
    Config.CONFIG_PATH = CONFIG_PATH

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    with SessionManager() as session_manager:
        request = Request(
            headers=CaseInsensitiveDict(
                {
                    "User-Agent": "schemathesis/4.15.2",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Accept": "*/*",
                    "Connection": "keep-alive",
                    "X-Schemathesis-TestCaseId": "g9cMS9",
                }
            ),
            body="",
            method=HTTPMethod("GET"),
            path="/greet?age=0&name=",
            query_parameters={"age": "0", "name": ""},
        )

        for _ in range(10):
            age = int(request.query_parameters["age"]) + 1
            request.query_parameters["age"] = str(age)
            result = session_manager.send(request)
            assert result.pop().request.query_parameters["age"] == str(age)


def test_mitmproxy_result_dir(monkeypatch):
    """Test obtaining a result from mitmproxy."""
    Config.CONFIG_PATH = CONFIG_PATH

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    with SessionManager() as session_manager:
        api_port = session_manager.sessions[BasicClient1.id].api.port
        api_url = f"http://localhost:{session_manager.mitmproxy.listen_port}"
        params = {"name": "Alice", "age": 30}
        assert (
            "Hello Alice, you are 30 years old!"
            in requests.get(
                f"{api_url}/localhost:{api_port}/greet",
                params=params,
            ).text
        ), "Message was not routed."

        result_files = os.listdir(session_manager.result_dir)
        assert len(result_files) == 1
        result_file = Path(session_manager.result_dir) / result_files[0]
        Request.from_json(result_file)
        Response.from_json(result_file)


def test_loop_same_library(monkeypatch):
    """Test the fuzzing loop with two instances of the basic client."""
    Config.CONFIG_PATH = CONFIG_PATH

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    fuzzer = TelePhuzz(TEST_OAS)
    fuzzer.start_fuzzing_session()

    assert len(os.listdir(LOG_PATH)) == 0
