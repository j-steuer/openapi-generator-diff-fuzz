"""File for code relating to request generation."""

import logging
import os
import signal
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from contextlib import ExitStack
from pathlib import Path
from time import sleep

from telephuzz.constants import BASE_PATH
from telephuzz.http_message import Request, Response
from telephuzz.session.mitm_proxy.mitm_proxy import MITMProxyContainer

SCHEMATHESIS_CONFIG_PATH = BASE_PATH / "schemathesis.toml"

logger = logging.getLogger(__name__)


class RequestGenerator(ABC):
    """Abstract class for the request generator."""

    @abstractmethod
    def generate(
        self, previous_responses: list[Response] | None = None
    ) -> list[Request] | None:
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
        proxy_port: int = 8081,
        batch_time: int | None = None,
        log_fuzzer: bool = False,
    ):
        """Pre-generate the requests using mitmproxy.

        Args:
            oas: The path to the OpenAPI specification used for generation.
            base_api_url: The base URL of the API (e.g. "http://localhost:8000")
            cmd: The cmd to be executed to start the fuzzer. Instead of the URL
                 of the API, the fuzzer should target "http://localhost:{proxy_port}"
                 WARNING: The provided cmd will be executed without sanitization.
                 Only provide trusted input.
            proxy_port: The port the mitmproxy instance (defaults to 8081)
            batch_time: If provided, instead of pregenerating all responses,
            pause and resume the process as needed for batch_time seconds.
            log_fuzzer: If true, display stdout and stderr messages produced by cmd

        """
        logger.info("Setting up fuzzer-based generator.")
        self.oas = oas
        self.pregenerated_requests: list[Request] = []
        self.batch_time = batch_time

        self.exit_stack = ExitStack()
        self.tmpdir = self.exit_stack.enter_context(tempfile.TemporaryDirectory())
        self.mitm_proxy = self.exit_stack.enter_context(
            MITMProxyContainer(
                response_output=self.tmpdir,
                listen_port=proxy_port,
                target=base_api_url,
            )
        )

        stdout = sys.stdout if log_fuzzer else subprocess.DEVNULL
        stderr = sys.stderr if log_fuzzer else subprocess.DEVNULL
        if self.batch_time is None:
            subprocess.run(
                cmd,
                stdout=stdout,
                stderr=stderr,
            )
        else:
            self.fuzzer_process = subprocess.Popen(cmd, stdout=stdout, stderr=stderr)
            sleep(self.batch_time)
            self._pause_fuzzer()
            self.first_collection = True

        logger.info("Finished generating requests.")

        self._collect_responses(Path(self.tmpdir))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.exit_stack.close()

    def _pause_fuzzer(self) -> None:
        """Pause the fuzzing process if fuzzer runs in batch mode."""
        if not self.batch_time:
            raise ValueError("Can only pause fuzzer if batch time provided.")

        pid = self.fuzzer_process.pid
        os.kill(pid, signal.SIGSTOP)

    def _resume_fuzzer(self) -> None:
        """Resume the fuzzing process if fuzzer runs in batch mode."""
        if not self.batch_time:
            raise ValueError("Can only resume fuzzer if batch time provided.")

        pid = self.fuzzer_process.pid
        os.kill(pid, signal.SIGCONT)

    def _collect_responses(self, dir_path: Path) -> None:
        """Collect and parse responses."""
        responses = os.listdir(dir_path)
        if len(responses) < 1:
            if not self.batch_time:
                raise ValueError(
                    "No responses were captured. "
                    "Your fuzzer needs to produce at least one request."
                )
            else:
                self.pregenerated_requests = list()

        base_response_path = Path(dir_path)
        for response in responses:
            response_path = base_response_path / response
            request_obj = Request.from_json(response_path)

            self.pregenerated_requests.append(request_obj)

    def generate(
        self, previous_responses: list[Response] | None = None
    ) -> list[Request] | None:
        """Return pregenerated requests in captured order until empty."""
        if self.batch_time is None:
            if not self.pregenerated_requests:
                return None

            if not hasattr(self, "total"):
                self.total = len(self.pregenerated_requests)

            request = self.pregenerated_requests.pop(0)
            return [request]

        else:
            if self.first_collection:
                self.first_collection = False
                return self.pregenerated_requests

            # clear previous requests
            for response_file in os.listdir(self.tmpdir):
                os.remove(os.path.join(self.tmpdir, response_file))
            self.pregenerated_requests = list()

            # collect more requests
            self._resume_fuzzer()
            sleep(self.batch_time)
            self._pause_fuzzer()

            self._collect_responses(Path(self.tmpdir))

            if not self.pregenerated_requests:
                return None

            return self.pregenerated_requests


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
        batch_time: int | None = None,
        log_fuzzer: bool = False,
    ):
        """Initialize the SchemathesisGenerator."""
        cmd = [
            "schemathesis",
            "--config-file",
            str(SCHEMATHESIS_CONFIG_PATH),
            "fuzz",
            str(oas),
            "--url",
            "http://localhost:8080",
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
            batch_time=batch_time,
        )
