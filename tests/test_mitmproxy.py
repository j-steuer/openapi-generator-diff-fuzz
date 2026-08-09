"""Tests for the mitmproxy container."""

import json
import os
import tempfile
from pathlib import Path

import pytest
import requests
from docker.models.networks import Network
from mitmproxy import http

from telephuzz.session.mitm_proxy import proxy_hooks_target
from telephuzz.session.mitm_proxy.mitm_proxy import MITMProxyContainer


@pytest.fixture
def basic_flow():
    request = http.Request.make(
        "POST",
        "https://example.com/api/test?foo=bar",
        '{"hello": "world"}',
        {
            "Content-Type": "application/json",
            "X-Test": "true",
        },
    )

    response = http.Response.make(
        200,
        '{"success": true}',
        {
            "Content-Type": "application/json",
        },
    )

    flow = http.HTTPFlow.__new__(http.HTTPFlow)
    flow.request = request
    flow.response = response

    return flow


def test_init() -> None:
    """Test initializing a mitmproxy container."""
    with MITMProxyContainer() as _:
        pass


def test_simple_routing(api: tuple[Network, str]) -> None:
    """Test routing a request via mitmproxy container."""
    params: dict = {"name": "Alice", "age": 30}

    network, _ = api

    with MITMProxyContainer() as mitm_proxy:
        assert mitm_proxy.container is not None
        network.connect(mitm_proxy.container)
        assert (
            requests.get(
                f"http://localhost:{mitm_proxy.listen_port}/greet",
                params=params,
            ).status_code
            == 200
        )


def test_simple_routing_multiple(api: tuple[Network, str]) -> None:
    """Test routing a request via mitmproxy container while multiple are running."""
    params: dict = {"name": "Alice", "age": 30}

    network, _ = api

    with MITMProxyContainer(listen_port=8080) as _:
        with MITMProxyContainer(listen_port=8081) as mitm_proxy:
            assert mitm_proxy.container is not None
            network.connect(mitm_proxy.container)
            assert (
                requests.get(
                    f"http://localhost:{mitm_proxy.listen_port}/greet",
                    params=params,
                ).status_code
                == 200
            )


def test_simple_routing_query_parameter(api: tuple[Network, str]) -> None:
    """Test routing a request with a query parameter via mitmproxy container."""
    params: dict = {"user_id": 1013}

    network, _ = api

    with tempfile.TemporaryDirectory() as tmpdir:
        with MITMProxyContainer(response_output=tmpdir) as mitm_proxy:
            assert mitm_proxy.container is not None
            network.connect(mitm_proxy.container)
            assert (
                requests.get(
                    f"http://localhost:{mitm_proxy.listen_port}/user",
                    params=params,
                ).status_code
                == 200
            )

            response_dir = Path(tmpdir) / "localhost"
            responses = os.listdir(response_dir)
            assert len(responses) == 1, "Should contain a single response file."
            response_file = responses[0]
            with open(Path(response_dir) / response_file) as f:
                entry_data = json.load(f)

            assert (
                entry_data["url"]
                == f"http://localhost:{mitm_proxy.listen_port}/user?user_id=1013"
            )


def test_json_response(api: tuple[Network, str]) -> None:
    """Test conversion of requests and responses into JSON."""
    params: dict = {"name": "Alice", "age": 30}

    network, _ = api

    with tempfile.TemporaryDirectory() as tmpdir:
        with MITMProxyContainer(response_output=tmpdir) as mitm_proxy:
            assert mitm_proxy.container is not None
            network.connect(mitm_proxy.container)
            requests.get(
                f"http://localhost:{mitm_proxy.listen_port}/greet",
                params=params,
            )

            respose_path = Path(tmpdir) / "localhost"
            responses = os.listdir(respose_path)
            assert len(responses) == 1, "Should contain a single response file."
            response_file = responses[0]
            with open(respose_path / response_file) as f:
                entry_data = json.load(f)

            assert entry_data["url"] == "http://localhost:8080/greet?name=Alice&age=30"


def test_single_target(api: tuple[Network, str]) -> None:
    """Test single target mode."""
    params: dict = {"name": "Alice", "age": 30}

    network, _ = api

    with tempfile.TemporaryDirectory() as tmpdir:
        with MITMProxyContainer(
            response_output=tmpdir, target="http://localhost:8000"
        ) as mitm_proxy:
            assert mitm_proxy.container is not None
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


def test_explode(basic_flow: http.HTTPFlow, monkeypatch) -> None:
    """Test that multiple items for a single query are resolved to an array."""
    basic_flow.request = http.Request.make(
        "GET",
        "https://example.com/search?tags=python&tags=mitmproxy&tags=testing&page=1",
    )

    with tempfile.TemporaryDirectory() as dir:
        monkeypatch.setattr(proxy_hooks_target, "RESPONSE_PATH", dir)

        proxy_hooks_target.response(basic_flow)
        file = os.listdir(dir)[0]
        with open(Path(dir) / file, "r") as f:
            data = json.load(f)

    query_parameters = data["request"]["query_parameters"]
    assert set(query_parameters["tags"]) == {
        "python",
        "mitmproxy",
        "testing",
    }
    assert query_parameters["page"] == "1"


def test_target_query_params():
    """Test extracting query params from targeted mitmproxy."""
