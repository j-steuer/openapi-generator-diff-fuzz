"""File for the main fuzzing loop."""

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import cast

import yaml  # type: ignore

from telephuzz.http_message import HTTPMethod
from telephuzz.operation_ids import generate_operation_id
from telephuzz.request_generator import RequestGenerator, SchemathesisGenerator


class TelePhuzz:
    """The main fuzzer class."""

    def __init__(
        self,
        oas: Path,
        request_generator: RequestGenerator | None = None,
        timeout: int | None = None,
    ) -> None:
        """Initialize a TelePhuzz instance.

        Args:
            oas: Path to the OpenAPI specification used for fuzzing.
            request_generator: The RequestGenerator to use (defaults to Schemathesis)
            timeout: The amount of time the fuzzer is to run in seconds.
            Runs until no more requests are generated if not set.

        """
        self.base_oas = oas
        self.processed_oas = oas

        self.request_generator = request_generator

        self.timeout = timeout

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
        if self.request_generator is None:
            # Use SchemathesisGenerator as default
            return SchemathesisGenerator(self.processed_oas)
        return self.request_generator  # TODO way to pass processed OAS

    def start_fuzzing_session(self) -> None:
        """Start the fuzzing session."""
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

            # fuzz until no more request( chain)s available or timeout has been reached
            while request is not None and (timeout is None or datetime.now() < timeout):
                pass  # TODO define fuzzing loop
