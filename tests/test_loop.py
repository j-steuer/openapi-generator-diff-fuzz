"""Tests for the entire fuzzing loop using custom clients and APIs."""

import textwrap
from pathlib import Path

from test_client import _init_and_send

from telephuzz.config import Config
from telephuzz.fuzzer import TelePhuzz
from telephuzz.http_message import Request
from telephuzz.session.client_library import OperationIdBasedCLC, PythonCLC

# TODO move somewhere else
TESTFILES = Path(__file__).parent / "testfiles"

CLIENT_PATH = TESTFILES / "test_clients"
BASIC_CLIENT_PATH = CLIENT_PATH / "basic_client"
TEST_OAS = TESTFILES / "openapi_test_fuzzing.json"
CONFIG_PATH = TESTFILES / "loop_config.yaml"


class BasicClient(PythonCLC, OperationIdBasedCLC):
    id = "test-client:python"

    def _get_code(self, request: Request, api_path: str) -> bytes:

        kwargs = f"api='{api_path}',"
        kwargs += ", ".join(
            f"{k}={repr(v)}" for k, v in request.query_parameters.items()
        )

        method_name = self._get_method_name(request)

        content = textwrap.dedent(f"""
        from pprint import pprint
                                  
        from telephuzz_basic_client.client import {method_name}
        
        pprint({self._get_method_name(request)}({kwargs}))
        """).encode()

        return content


def test_basic_client(api):
    """Test that basic client works."""
    with BasicClient(library_path=BASIC_CLIENT_PATH) as basic_client:
        _init_and_send(basic_client, api)


def test_loop_same_library(monkeypatch):
    """Test the fuzzing loop with two instances of the basic client."""

    Config.CONFIG_PATH = CONFIG_PATH

    class BasicClient1(BasicClient):
        id = "test-client1:python"

    class BasicClient2(BasicClient):
        id = "test-client2:python"

    monkeypatch.setattr("telephuzz.session.session.CLIENT_PATH", CLIENT_PATH)

    fuzzer = TelePhuzz(TEST_OAS)
    fuzzer.start_fuzzing_session()
