"""Tests for the mitmproxy container."""

import requests

from telephuzz.session.mitm_proxy.mitm_proxy import MITMProxyContainer


def test_mitm_proxy_init() -> None:
    """Test initializing a mitmproxy container."""
    with MITMProxyContainer() as _:
        pass


def test_mitm_proxy_intercept(api) -> None:
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
