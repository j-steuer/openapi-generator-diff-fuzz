"""File for the container with MiTMProxy."""

import socket
import time
from copy import deepcopy
from pathlib import Path

import docker
from docker.models.containers import Container

from telephuzz.http_message import Request
from telephuzz.session.mitm_proxy.proxy_hooks import RESPONSE_PATH

DEFAULT_LISTEN_PORT = 8080
SCRIPTS_DYNAMIC = (Path(__file__).resolve().parent / "proxy_hooks.py").absolute()
SCRIPTS_TARGET = (Path(__file__).resolve().parent / "proxy_hooks_target.py").absolute()


class MITMProxyContainer:
    """Class for the MiTMProxy container."""

    container: Container | None

    def __init__(
        self,
        version: str = "12.2.2",
        listen_port: int = DEFAULT_LISTEN_PORT,
        response_output: str = "/tmp/telephuzz-mitmproxy-responses",
        target: str | None = None,
    ) -> None:
        """Set up the proxy container and add it to the network."""
        self.listen_port = listen_port
        self.response_output = response_output

        client = docker.from_env()
        hooks_path = "/scripts/hooks.py"

        if target is None:
            # dynamic routing mode (used for main fuzzing loop)
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
                    str(SCRIPTS_DYNAMIC): {"bind": hooks_path, "mode": "ro"},
                    response_output: {"bind": RESPONSE_PATH, "mode": "rw"},
                },
            )

        else:
            # single target mode (used for pre-generating requests)
            container = client.containers.run(
                image=f"mitmproxy/mitmproxy:{version}",
                command=[
                    "mitmdump",
                    "--mode",
                    f"reverse:{target}",
                    "--listen-port",
                    str(self.listen_port),
                    "--script",
                    hooks_path,
                ],
                network_mode="host",  # TODO replace?
                detach=True,
                volumes={
                    str(SCRIPTS_TARGET): {"bind": hooks_path, "mode": "ro"},
                    response_output: {"bind": RESPONSE_PATH, "mode": "rw"},
                },
            )

        assert container is not None, (
            "Container should be created and run in detached mode!"
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
            self.container.kill()
        finally:
            self.container.remove(force=True)
            self.container = None

    def through_proxy(self, request: Request, library_port: int) -> Request:
        """Make the request target the proxy and encode the target."""
        new_request = deepcopy(request)
        extra_slash = "/" if not request.path.startswith("/") else ""
        new_request.path = f"/localhost:{library_port}{extra_slash}{request.path}"
        new_request.path = new_request.path.replace("localhost", "host.docker.internal")
        return new_request
