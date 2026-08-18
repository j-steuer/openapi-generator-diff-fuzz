"""File for code relating to request generation."""

import logging
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from abc import ABC, abstractmethod
from contextlib import ExitStack
from pathlib import Path

from telephuzz.constants import BASE_PATH
from telephuzz.http_message import Request
from telephuzz.session.mitm_proxy.mitm_proxy import MITMProxyContainer

SCHEMATHESIS_CONFIG_PATH = BASE_PATH / "schemathesis.toml"

logger = logging.getLogger(__name__)


class RequestGenerator(ABC):
    """Abstract class for the request generator."""

    @abstractmethod
    def generate(self) -> list[Request] | None:
        """Abstract method for generating a request chain."""
        raise NotImplementedError


class OASRequestGenerator(RequestGenerator):
    """Abstract class for a request generator that takes an OpenAPI spec as input."""

    oas: Path


class FuzzerBasedGenerator(OASRequestGenerator):
    """Use an OpenAPI-based fuzzer to pre-generate a sequence of requests.

    Depending on the fuzzer, this process may take a long time.
    """

    pregenerated_requests: list[Request]

    def __init__(
        self,
        oas: Path,
        base_api_url: str,
        cmd: list[str],
        proxy_port: int = 8080,
        log_fuzzer: bool = False,
        batch_interval: int = 10,
        batch_size: int = 100,
    ):
        """Pre-generate the requests using mitmproxy.

        Args:
            oas: The path to the OpenAPI specification used for generation.
            base_api_url: The base URL of the API (e.g. "http://localhost:8000")
            cmd: The cmd to be executed to start the fuzzer. Instead of the URL
                 of the API, the fuzzer should target "http://localhost:{proxy_port}"
                 WARNING: The provided cmd will be executed without sanitization.
                 Only provide trusted input.
            proxy_port: The port the mitmproxy instance (defaults to 8080)
            log_fuzzer: If true, display stdout and stderr messages produced by cmd
            batch_interval: time in seconds to run the fuzzer asynchronously at a time
            batch_size: number of requests to hand collect at once

        """
        logger.info("Setting up fuzzer-based generator.")
        self.oas = oas
        self.batch_interval = batch_interval
        self.batch_size = batch_size
        self.pregenerated_requests: list[Request] = []

        self.exit_stack = ExitStack()

        self.tmpdir = self.exit_stack.enter_context(tempfile.TemporaryDirectory())
        self.mitmproxy = self.exit_stack.enter_context(
            MITMProxyContainer(
                response_output=self.tmpdir, listen_port=proxy_port, target=base_api_url
            )
        )

        self.fuzzing_process = subprocess.Popen(
            cmd,
            stdout=sys.stdout if log_fuzzer else subprocess.DEVNULL,
            stderr=sys.stderr if log_fuzzer else subprocess.DEVNULL,
            start_new_session=True,  # for handling potential child processes
        )

        self.running = True

        attempts = 100
        while len(os.listdir(self.tmpdir)) < 1:
            time.sleep(0.1)
            attempts -= 1
            if not attempts:
                raise TimeoutError(
                    "No responses were captured. "
                    "Your fuzzer needs to produce at least one request."
                )

        # start generating asynchronously
        self.pause()
        self.run()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exit_stack.close()

    def pause(self):
        """Pause the fuzzing process."""
        if not self.running:
            return
        os.killpg(self.fuzzing_process.pid, signal.SIGSTOP)
        self.running = False

    def resume(self):
        "Resume the fuzzing process."
        if self.running:
            return
        os.killpg(self.fuzzing_process.pid, signal.SIGCONT)
        self.running = True

    def run(self):
        """Run the fuzzing process asynchronously for batch_interval seconds."""
        self.resume()

        def _pause_after():
            time.sleep(self.batch_interval)
            if self.fuzzing_process.poll() is None:  # still running
                self.pause()

        threading.Thread(target=_pause_after, daemon=True).start()

    def _collect_responses(self):
        """Collect latest responses."""
        responses = os.listdir(self.tmpdir)
        base_response_path = Path(self.tmpdir)
        for response in responses[: self.batch_size]:
            response_path = base_response_path / response
            request_obj = Request.from_json(response_path)

            self.pregenerated_requests.append(request_obj)

            os.remove(response_path)

        # start generating requests again when running low and not already generating
        if len(responses) < self.batch_size and not self.running:
            self.run()

    def generate(self) -> list[Request] | None:
        """Return pregenerated requests in captured order until empty."""
        if not self.pregenerated_requests:
            self._collect_responses()

            while not self.pregenerated_requests:
                if self.fuzzing_process.poll() is not None:
                    # fuzzing process finished and requests exhausted
                    return None

                if not self.running:
                    # resume process until it produces requests or terminates
                    self.run()

                time.sleep(1)

        if not hasattr(self, "total"):
            self.total = len(self.pregenerated_requests)

        request = self.pregenerated_requests.pop(0)

        return [request]


class SchemathesisGenerator(FuzzerBasedGenerator):
    """Request generator based on Schemathesis.

    Pre-generates all requests using a standard Schemathesis run,
    so it will take a while to start the core fuzzing loop.
    """

    def __init__(
        self,
        oas: Path,
        base_api_url: str,
        proxy_port: int = 8080,
        max_time_seconds: int = 3600,
        log_fuzzer: bool = False,
        batch_interval: int = 10,
        batch_size: int = 100,
    ):
        """Initialize the SchemathesisGenerator."""
        cmd = [
            "schemathesis",
            "--config-file",
            str(SCHEMATHESIS_CONFIG_PATH),
            "fuzz",
            str(oas),
            "--url",
            f"http://localhost:{proxy_port}",
            "--max-time",
            str(max_time_seconds),
            "--continue-on-failure",
            "-m",
            "positive",
        ]
        super().__init__(
            oas=oas,
            base_api_url=base_api_url,
            cmd=cmd,
            proxy_port=proxy_port,
            log_fuzzer=log_fuzzer,
            batch_interval=batch_interval,
            batch_size=batch_size,
        )
