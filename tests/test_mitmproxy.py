"""Tests for the mitmproxy container."""

import json
import os
import tempfile
from pathlib import Path

import requests

from telephuzz.session.mitm_proxy.mitm_proxy import MITMProxyContainer


def test__init() -> None:
    """Test initializing a mitmproxy container."""
    with MITMProxyContainer() as _:
        pass


def test_simple_routing(api) -> None:
    """Test routing a request via mitmproxy container."""
    params: dict = {"name": "Alice", "age": 30}

    with MITMProxyContainer() as mitm_proxy:
        assert (
            "Hello Alice, you are 30 years old!"
            in requests.get(
                f"http://localhost:{mitm_proxy.listen_port}/localhost:8000/greet",
                params=params,
            ).text
        )


def test_json_response(api) -> None:
    """Test conversion of requests and responses into JSON."""
    params: dict = {"name": "Alice", "age": 30}

    with tempfile.TemporaryDirectory() as tmpdir:
        with MITMProxyContainer(response_output=tmpdir) as mitm_proxy:
            requests.get(
                f"http://localhost:{mitm_proxy.listen_port}/localhost:8000/greet",
                params=params,
            )

            responses = os.listdir(tmpdir)
            assert len(responses) == 1, "Should contain a single response file."
            response_file = responses[0]
            with open(Path(tmpdir) / response_file) as f:
                entry_data = json.load(f)

            assert (
                "Hello Alice, you are 30 years old!" in entry_data["response"]["body"]
            )


def test_single_target(api) -> None:
    """Test single target mode."""
    params: dict = {"name": "Alice", "age": 30}

    with tempfile.TemporaryDirectory() as tmpdir:
        with MITMProxyContainer(
            response_output=tmpdir, target="http://localhost:8000"
        ) as mitm_proxy:
            assert (
                "Hello Alice, you are 30 years old!"
                in requests.get(
                    f"http://localhost:{mitm_proxy.listen_port}/greet",
                    params=params,
                ).text
            ), "Request was not routed correctly."

        responses = os.listdir(tmpdir)
        assert len(responses) == 1, "Should contain a single response file."
        response_file = responses[0]
        with open(Path(tmpdir) / response_file) as f:
            entry_data = json.load(f)

        assert "Hello Alice, you are 30 years old!" in entry_data["response"]["body"]
