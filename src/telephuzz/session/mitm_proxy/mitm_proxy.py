"""File for the container with MiTMProxy."""

import os
import shutil
import socket
import time
from pathlib import Path

import docker
import requests
from docker.models.containers import Container

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

        # set up response path
        response_path = Path(self.response_output)
        if response_path.exists() and len(os.listdir(response_path)) != 0:
            shutil.rmtree(response_path)
        os.makedirs(response_path, exist_ok=True)

        self.target = target
        if self.target is None:
            # set up without target, returning dummy response through hook
            container = client.containers.run(
                image=f"mitmproxy/mitmproxy:{version}",
                command=[
                    "mitmdump",
                    "--listen-port",
                    str(self.listen_port),
                    "--script",
                    hooks_path,
                ],
                ports={f"{self.listen_port}/tcp": self.listen_port},
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
                network_mode="host",
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

        latest_error = None
        while time.time() - start < timeout:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("localhost", self.listen_port)) == 0:
                    if self.target is not None:
                        return
                    try:
                        if (
                            requests.get(
                                f"http://localhost:{self.listen_port}/__mitmproxy_health"
                            ).status_code
                            == 200
                        ):
                            return
                    except Exception as e:
                        latest_error = e
                else:
                    time.sleep(0.2)
        # timeout
        if latest_error is None:
            raise RuntimeError("mitmproxy did not become ready in time.")
        else:
            raise RuntimeError("Could not start mitmproxy") from latest_error

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
