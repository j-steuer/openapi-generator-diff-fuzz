"""Helper methods for reading and processing an OpenAPI spec."""

import json
from pathlib import Path
from typing import cast

import yaml  # type: ignore

from telephuzz.http_message import HTTPMethod
from telephuzz.operation_ids import generate_operation_id


def preprocess_oas(oas: Path, output_path: Path) -> None:
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
            raise ValueError("Only .json and .yaml OpenAPI spec files are supported.")

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
