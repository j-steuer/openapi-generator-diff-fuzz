"""Tests for the entire fuzzing loop using custom clients and APIs."""

import json
import os
import textwrap
from json import JSONDecodeError
from pathlib import Path
from time import sleep

import docker
import pytest
import requests
from conftest import TEST_CONFIG_BASE_PATH
from docker.models.networks import Network
from requests.models import CaseInsensitiveDict

from telephuzz.config import Config
from telephuzz.evaluation.evaluator import DiffEvaluator
from telephuzz.fuzzer import TelePhuzz
from telephuzz.http_message import HTTPMethod, Request
from telephuzz.invocation_data import InvocationData
from telephuzz.session.client_library import (
    ClientLibraryContainer,
    ModelCode,
    OpenAPIVersion,
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


BASIC_CLIENT = "basicclient"
BASIC_FAULTY_CLIENT = "basicfaultyclient"
BASIC_CLIENT_REQUEST = Request(
    headers=CaseInsensitiveDict({"Test": ["test"]}),
    body=None,
    method=HTTPMethod.GET,
    path="/greet",
    query_parameters={"name": "Alice", "age": 30},
)


def _init_and_send(clc: ClientLibraryContainer, api: str, auth: bool = False):
    """Initialize and send basic message to test API."""
    client = docker.from_env()
    assert clc.container is not None
    id = clc.container.id
    assert id is not None
    container = client.containers.get(id)
    assert container.status == "running"

    request = Request(
        headers=CaseInsensitiveDict({"Test": ["test"]}),
        body=None,
        method=HTTPMethod.GET,
        path="/greet",
        query_parameters={"name": "Alice", "age": 30},
    )

    if auth:
        request.headers["Authorization"] = "mock-token"

    clc.send(InvocationData(request), api)
    sleep(1)
    assert "Hello Alice, you are 30 years old!" in clc.container.logs().decode()


class BasicClient(PythonCLC, OperationIdBasedCLC):
    id = "basicclient"
    generator_script = "basic-client.sh"
    supported_versions = {OpenAPIVersion.V_3_1}

    def _generate_code_models(self, invocation: InvocationData) -> ModelCode:
        return ModelCode(import_code="", creation_code="")

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
    generator_script = "basic-faulty-client.sh"


def test_basic_client(api: tuple[Network, str]):
    """Test that basic client works."""
    network, api_path = api
    with BasicClient() as basic_client:
        assert basic_client.container is not None
        network.connect(basic_client.container)
        sleep(1)
        _init_and_send(basic_client, api_path)


def test_faulty_client(api: tuple[Network, str]):
    """Test that faulty client does not send messages correctly."""
    network, api_path = api
    with BasicFaultyClient() as basic_client:
        assert basic_client.container is not None
        network.connect(basic_client.container)
        sleep(1)
        with pytest.raises(AssertionError, match="Hello Faulty, you are 42"):
            _init_and_send(basic_client, api_path)


def test_session_manager_faulty():
    """Test setting up session manager with faulty client."""
    Config.API_CONFIG_PATH = API_CONFIG_PATH

    with SessionManager(BASIC_FAULTY_CLIENT) as session_manager:
        assert len(session_manager.sessions) == 1
        assert BASIC_FAULTY_CLIENT in session_manager.sessions

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
            body=b"",
            method=HTTPMethod.GET,
            path="/greet?age=0&name=",
            query_parameters={"age": "0", "name": ""},
        )

        results = session_manager.send(request=request)
        assert any("Faulty" in repr(r) for r in results), results


def test_diff_eval(tmp_path):
    """Test capturing and evaluating a result."""
    Config.API_CONFIG_PATH = API_CONFIG_PATH

    with SessionManager(BASIC_CLIENT) as session_manager:
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
            body=b"",
            method=HTTPMethod.GET,
            path="/greet?age=0&name=",
            query_parameters={"age": "0", "name": ""},
        )

        # attempt to send with session manager
        results = session_manager.send(request)
        assert len(results) == 1

        evaluator = DiffEvaluator(tmp_path)
        evaluator.eval(results, request)

        assert len(os.listdir(evaluator.log_path)) == 0


def test_mitmproxy_result_dir():
    """Test obtaining a result from mitmproxy."""
    Config.API_CONFIG_PATH = API_CONFIG_PATH

    with SessionManager(BASIC_CLIENT) as session_manager:
        api_url = f"http://localhost:{session_manager.mitmproxy.listen_port}"
        params = {"name": "Alice", "age": 30}
        assert (
            "OK"
            in requests.get(
                f"{api_url}/api0:8000/greet",
                params=params,
            ).text
        ), "Message was not routed."

        result_dir = Path(session_manager.result_dir) / "localhost"
        result_files = os.listdir(result_dir)
        assert len(result_files) == 1
        result_file = result_dir / result_files[0]
        Request.from_json(result_file)


def test_loop_same_library(tmp_path):
    """Test the fuzzing loop with two instances of the basic client."""
    Config.API_CONFIG_PATH = API_CONFIG_PATH

    fuzzer = TelePhuzz(BASIC_CLIENT, tmp_path, timeout=10)
    fuzzer.start_fuzzing_session()

    assert len(os.listdir(tmp_path)) == 0


def test_loop_faulty_library(tmp_path):
    """Test the fuzzing loop with two instances of the basic client."""
    Config.API_CONFIG_PATH = API_CONFIG_PATH

    fuzzer = TelePhuzz(BASIC_FAULTY_CLIENT, tmp_path, timeout=10)
    fuzzer.start_fuzzing_session()

    assert len(os.listdir(tmp_path)) > 0


def test_send_petshop():

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

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
        body=b"",
        method=HTTPMethod.GET,
        path="/store/inventory",
        query_parameters={},
    )

    with SessionManager("openapi-generator:python") as session_manager:
        results = session_manager.send(request)
        assert len(results) == 1


def test_obtain_jacoco_coverage(tmp_path):
    """Test that jacoco coverage is captured at the end of the fuzzing loop."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

    fuzzer = TelePhuzz("openapi-generator:python", tmp_path, timeout=2)
    fuzzer.start_fuzzing_session()

    # check that jacoco file was created
    coverage_path = "./reports/coverage/api_petshop_config"
    assert len(os.listdir(coverage_path)) == 1
    assert os.listdir(coverage_path)[0] == "jacoco.exec"
