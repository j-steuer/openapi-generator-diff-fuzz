"""File for code relating to request generation."""

import logging
import os
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

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
        proxy_port: int = 8080,
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
            proxy_port: The port the mitmproxy instance (defaults to 8080)
            log_fuzzer: If true, display stdout and stderr messages produced by cmd

        """
        logger.info("Setting up fuzzer-based generator.")
        self.oas = oas
        self.pregenerated_requests: list[Request] = []

        with tempfile.TemporaryDirectory() as tmpdir:
            with MITMProxyContainer(
                response_output=tmpdir, listen_port=proxy_port, target=base_api_url
            ) as _:
                subprocess.run(
                    cmd,
                    stdout=sys.stdout if log_fuzzer else subprocess.DEVNULL,
                    stderr=sys.stderr if log_fuzzer else subprocess.DEVNULL,
                )

            logger.info("Finished generating requests.")

            responses = os.listdir(tmpdir)
            if len(responses) < 1:
                raise ValueError(
                    "No responses were captured. "
                    "Your fuzzer needs to produce at least one request."
                )

            base_response_path = Path(tmpdir)
            for response in responses:
                response_path = base_response_path / response
                request_obj = Request.from_json(response_path)

                self.pregenerated_requests.append(request_obj)

    def generate(
        self, previous_responses: list[Response] | None = None
    ) -> list[Request] | None:
        """Return pregenerated requests in captured order until empty."""
        if not self.pregenerated_requests:
            return None

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
        )
