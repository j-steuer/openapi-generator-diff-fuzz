"""File for the main fuzzing loop."""

import json
import logging
import os
import tempfile
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep
from typing import cast

import requests
import yaml  # type: ignore

from telephuzz.config import get_config
from telephuzz.docker_helpers import compose_down, compose_up, set_port_env
from telephuzz.evaluation.evaluator import DiffEvaluator
from telephuzz.http_message import HTTPMethod
from telephuzz.logging_config import setup_logging
from telephuzz.operation_ids import generate_operation_id
from telephuzz.request_generator import (
    FuzzerBasedGenerator,
    RequestGenerator,
    SchemathesisGenerator,
)
from telephuzz.session.session import SessionManager

setup_logging()
logger = logging.getLogger(__name__)

SCHEMATHESIS_PROJECT = "schemathesis_project"


class TelePhuzz:
    """The main fuzzer class."""

    def __init__(
        self, oas: Path, request_generator: RequestGenerator | None = None
    ) -> None:
        """Initialize a TelePhuzz instance.

        Args:
            oas: Path to the OpenAPI specification used for fuzzing.
            request_generator: The RequestGenerator to use (defaults to Schemathesis)
            timeout: The amount of time the fuzzer is to run in seconds.
            request_generator_api_url: The URL of the API to generate requests from
            when using a fuzzer-based generator.
            Runs until no more requests are generated if not set.

        """
        logging.info("Initializing fuzzing session.")
        self.base_oas = oas
        self.processed_oas = oas

        self.request_generator = request_generator
        self.evaluator = DiffEvaluator()

        self.timeout = get_config().timeout

        self.exit_stack = ExitStack()

    def _preprocess_oas(self, oas: Path, output_path: Path) -> None:
        """Pre-process an OpenAPI spec and map all paths to own operationId.

        Writes the resulting OpenAPI spec to output_path.
        """
        match oas.suffix:
            case ".json":
                with open(oas) as f:
                    spec = json.load(f)
            case ".yaml" | ".yml":
                with open(oas) as f:
                    spec = yaml.safe_load(f)
            case _:
                raise ValueError(
                    "Only .json and .yaml OpenAPI spec files are supported."
                )

        assert isinstance(spec, dict), "OpenAPI spec was not loaded as a dict"
        spec = cast(dict[str, dict], spec)
        for path, methods in spec.get("paths", {}).items():
            assert isinstance(methods, dict), "Methods were not loaded as a dict"
            methods = cast(dict[str, dict], methods)
            for method, operation in methods.items():
                try:
                    HTTPMethod(method)
                except ValueError:
                    # ignore non-method keys like parameters
                    continue
                operation["operationId"] = generate_operation_id(method, path)

        with open(output_path, "w") as f:
            if output_path.suffix == ".json":
                json.dump(spec, f)
            elif output_path.suffix == ".yaml":
                yaml.safe_dump(spec, f)

    def _setup_request_generator(self) -> RequestGenerator:
        """Set up the request generator."""
        logging.info("Setting up request generator.")
        if self.request_generator is None:
            logging.info("No request generator provided, using default generator.")
            # start up example API
            config = get_config()
            env = set_port_env({config.api_port_name: 8000})
            compose_up(config.compose_path, env=env, project=SCHEMATHESIS_PROJECT)

            # check that API server is ready
            timeout = 5
            for i in range(timeout + 1):
                try:
                    if (
                        requests.get(
                            "http://localhost:8000/openapi.json",
                            timeout=1,
                        ).status_code
                        == 200
                    ):
                        break
                except requests.RequestException:
                    pass

                if i == timeout:
                    raise TimeoutError("API server did not start in time.")
                sleep(1)

            # Use SchemathesisGenerator as default
            generator = self.exit_stack.enter_context(
                SchemathesisGenerator(
                    self.processed_oas,
                    "http://localhost:8000",
                    max_time_seconds=self.timeout if self.timeout else 3600,
                    proxy_port=8081,
                )
            )
            return generator
        return self.request_generator  # TODO way to pass processed OAS

    def start_fuzzing_session(self) -> None:
        """Start the fuzzing session."""
        logger.info("Starting fuzzing session.")
        with tempfile.TemporaryDirectory() as tmpdir:
            # pre-process OAS
            self.processed_oas = Path(
                os.path.join(tmpdir, f"oas{self.base_oas.suffix}")
            )
            self._preprocess_oas(self.base_oas, self.processed_oas)

            # set up request generator
            self.request_generator = self._setup_request_generator()

            # compute timeout if set
            timeout = (
                datetime.now() + timedelta(seconds=self.timeout)
                if self.timeout
                else None
            )

            # generate first request (chain)
            request = self.request_generator.generate()
            if not request:
                raise ValueError(
                    "Specified request generator must generate at least one request!"
                )

            with SessionManager() as session_manager:
                # fuzz until no more request( chain)s available or timeout
                logger.info("Beginning to fuzz clients.")
                use_timeout = timeout is not None and not isinstance(
                    self.request_generator, FuzzerBasedGenerator
                )
                while request is not None:
                    # TODO previous responses
                    request = self.request_generator.generate()
                    if request is None:
                        continue

                    for current_request in request:
                        results = session_manager.send(current_request)
                        self.evaluator.eval(results, current_request)

                    if use_timeout:
                        assert timeout is not None
                        if datetime.now() >= timeout:
                            break

        if isinstance(self.request_generator, FuzzerBasedGenerator):
            self.exit_stack.close()
            compose_down(get_config().compose_path, project=SCHEMATHESIS_PROJECT)
