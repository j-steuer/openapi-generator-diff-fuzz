"""File for the container with MiTMProxy."""

import socket
import time
from copy import deepcopy
from pathlib import Path

import docker
from docker.models.containers import Container

from telephuzz.http_message import Request
from telephuzz.session.client_library import LibraryId
from telephuzz.session.mitm_proxy.proxy_hooks import RESPONSE_PATH

DEFAULT_LISTEN_PORT = 8080
SCRIPTS = (Path(__file__).resolve().parent / "proxy_hooks.py").absolute()


class MITMProxyContainer:
    """Class for the MiTMProxy container."""

    container: Container | None

    def __init__(
        self,
        version: str = "12.2.2",
        listen_port: int = DEFAULT_LISTEN_PORT,
        response_output: str = "/tmp/telephuzz-mitmproxy-responses",
    ) -> None:
        """Set up the proxy container and add it to the network."""
        self.listen_port = listen_port
        self.response_output = response_output

        client = docker.from_env()

        hooks_path = "/scripts/hooks.py"

        container = client.containers.run(
            image=f"mitmproxy/mitmproxy:{version}",
            command=[
                "mitmdump",
                "--listen-port",
                str(self.listen_port),
                "--script",
                hooks_path,
            ],
            network_mode="host",  # TODO replace?
            detach=True,
            volumes={
                str(SCRIPTS): {"bind": hooks_path, "mode": "ro"},
                response_output: {"bind": RESPONSE_PATH, "mode": "rw"},
            },
        )

        self.container = container

    def _wait_until_ready(self, timeout: float = 10.0) -> None:
        start = time.time()

        while time.time() - start < timeout:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("localhost", self.listen_port)) == 0:
                    return
                else:
                    time.sleep(0.2)
        # timeout
        raise RuntimeError("mitmproxy did not become ready in time.")

    def __enter__(self):
        """Make mitmproxy container a context manager."""
        self._wait_until_ready()
        return self

    def __exit__(self, exc_type, exc, tb):
        """Run close method when context ends."""
        self.close()

    def close(self) -> None:
        """Kill the container after context ends."""
        if self.container is None:
            return

        try:
            self.container.kill()  # immediate, deterministic
        finally:
            self.container.remove(force=True)
            self.container = None

    def through_proxy(
        self, request: Request, library_id: LibraryId, library_port: int
    ) -> Request:
        """Make the request target the proxy and encode the target."""
        new_request = deepcopy(request)
        new_request.path = f"/{library_id}:{library_port}/{request.path}"
        return new_request
