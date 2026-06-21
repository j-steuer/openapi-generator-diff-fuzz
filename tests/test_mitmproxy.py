"""Tests for the mitmproxy container."""

import json
import os
import tempfile
from pathlib import Path
from time import sleep

import requests
from docker.models.networks import Network

from telephuzz.session.mitm_proxy.mitm_proxy import MITMProxyContainer


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
        sleep(1)
        assert (
            "Hello Alice, you are 30 years old!"
            in requests.get(
                f"http://localhost:{mitm_proxy.listen_port}/api:8000/greet",
                params=params,
            ).text
        )


def test_simple_routing_custom_port(api: tuple[Network, str]) -> None:
    """Test routing a request via mitmproxy container with non-default port."""
    params: dict = {"name": "Alice", "age": 30}

    network, _ = api

    with MITMProxyContainer(listen_port=8081) as mitm_proxy:
        assert mitm_proxy.container is not None
        network.connect(mitm_proxy.container)
        sleep(1)
        assert (
            "Hello Alice, you are 30 years old!"
            in requests.get(
                f"http://localhost:{mitm_proxy.listen_port}/api:8000/greet",
                params=params,
            ).text
        )


def test_simple_routing_multiple(api: tuple[Network, str]) -> None:
    """Test routing a request via mitmproxy container while multiple are running."""
    params: dict = {"name": "Alice", "age": 30}

    network, _ = api

    with MITMProxyContainer(listen_port=8080) as _:
        with MITMProxyContainer(listen_port=8081) as mitm_proxy:
            assert mitm_proxy.container is not None
            network.connect(mitm_proxy.container)
            sleep(1)
            assert (
                "Hello Alice, you are 30 years old!"
                in requests.get(
                    f"http://localhost:{mitm_proxy.listen_port}/api:8000/greet",
                    params=params,
                ).text
            )


def test_simple_routing_query_parameter(api: tuple[Network, str]) -> None:
    """Test routing a request with a query parameter via mitmproxy container."""
    params: dict = {"user_id": 1013}

    network, _ = api

    with MITMProxyContainer() as mitm_proxy:
        assert mitm_proxy.container is not None
        network.connect(mitm_proxy.container)
        sleep(1)
        assert (
            "This is a GET request returning user info"
            in requests.get(
                f"http://localhost:{mitm_proxy.listen_port}/api:8000/user?user_id=1013",
                params=params,
            ).text
        )


def test_json_response(api: tuple[Network, str]) -> None:
    """Test conversion of requests and responses into JSON."""
    params: dict = {"name": "Alice", "age": 30}

    network, _ = api

    with tempfile.TemporaryDirectory() as tmpdir:
        with MITMProxyContainer(response_output=tmpdir) as mitm_proxy:
            assert mitm_proxy.container is not None
            network.connect(mitm_proxy.container)
            sleep(1)
            requests.get(
                f"http://localhost:{mitm_proxy.listen_port}/api:8000/greet",
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


def test_single_target(api: tuple[Network, str]) -> None:
    """Test single target mode."""
    params: dict = {"name": "Alice", "age": 30}

    network, _ = api

    with tempfile.TemporaryDirectory() as tmpdir:
        with MITMProxyContainer(
            response_output=tmpdir, target="http://api:8000"
        ) as mitm_proxy:
            assert mitm_proxy.container is not None
            network.connect(mitm_proxy.container)
            sleep(1)
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
