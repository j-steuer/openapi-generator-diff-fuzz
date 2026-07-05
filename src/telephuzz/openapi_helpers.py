"""Helper methods for reading and processing an OpenAPI spec."""

import json
from functools import cache
from pathlib import Path
from typing import Any, cast
from urllib.parse import ParseResult, urlparse

import yaml  # type: ignore

from telephuzz.config import get_config
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


def _find_all(spec: dict, element: str) -> list[Any]:
    """Find all instances of element in the spec."""
    results = []

    if isinstance(spec, dict):
        for k, v in spec.items():
            if k == element:
                results.append(v)
            else:
                results.extend(_find_all(v, element))

    return results


def find_operation(spec: dict, operation_id: str) -> dict | None:
    """Find operation with operation id."""

    if isinstance(spec, dict):
        for v in spec.values():
            if not isinstance(v, dict):
                continue
            if "operationId" in v and v["operationId"] == operation_id:
                return v
            else:
                rec_search = find_operation(v, operation_id)
                if rec_search is not None:
                    return rec_search

    return None


@cache
def get_args(method: HTTPMethod, path: str) -> str | None:
    """Obtain a list of arguments for the given operation id."""
    # search operation id
    spec = get_config().spec
    operation_id = resolve_request_id(method, path, json.dumps(spec))
    operation = find_operation(spec, operation_id)

    if operation is None:
        return None

    assert isinstance(operation, dict)
    # get request body
    if "requestBody" in operation:
        content = operation["requestBody"]["content"]
        _ref = set(_find_all(content, "$ref"))
        assert len(_ref) == 1
        ref = _ref.pop()
        assert isinstance(ref, str)
        return ref[ref.rfind("/") + 1 :].capitalize()

    return None


def get_api_url_path(spec: dict | None = None) -> str:
    """Obtain the base path of the API.

    Spec can either be provided directly or read from config if not provided."""
    if spec is None:
        spec = get_config().spec

    assert isinstance(spec, dict)
    if "servers" not in spec:
        return ""

    url = spec["servers"][0]["url"]
    parsed_url = urlparse(url)

    assert isinstance(parsed_url, ParseResult)
    path = parsed_url.path

    assert isinstance(path, str)
    return path


@cache
def extract_paths(spec_json: str) -> tuple[set[str], set[str]]:
    spec: dict = json.loads(spec_json)

    concrete = set()
    non_concrete = set()

    for path in spec.get("paths", {}):
        if "{" in path and "}" in path:
            non_concrete.add(path)
        else:
            concrete.add(path)

    return concrete, non_concrete


def resolve_path(
    path: str, concrete_paths: set[str], non_concrete_paths: set[str]
) -> str:
    """
    Resolve an incoming API path to:
    1. Exact match in concrete paths, or
    2. Best match among non-concrete paths, or
    3. Raise error if no match found
    """

    # 1. Exact match
    if path in concrete_paths:
        return path

    path_parts = _split(path)

    best_match = None
    best_score = (-1, float("inf"))  # (static_matches, wildcard_count)

    # 2. Match against templates
    for template in non_concrete_paths:
        tpl_parts = _split(template)

        if len(tpl_parts) != len(path_parts):
            continue

        static_matches = 0
        wildcard_count = 0
        matches = True

        for p_seg, t_seg in zip(path_parts, tpl_parts, strict=False):
            if _is_param(t_seg):
                wildcard_count += 1
                continue
            if p_seg == t_seg:
                static_matches += 1
            else:
                matches = False
                break

        if matches:
            score = (static_matches, -wildcard_count)
            if score > best_score:
                best_score = score
                best_match = template

    if best_match:
        return best_match

    raise ValueError(f"No matching path found for: {path}")


def _is_param(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def _split(path: str) -> list[str]:
    return [p for p in path.strip("/").split("/") if p]


def resolve_request_id(method: HTTPMethod, path: str, spec_str: str) -> str:
    operation_id = generate_operation_id(method.value, path)

    concrete, non_concrete = extract_paths(spec_str)
    if "?" in path:
        path_only = path[: path.find("?")]
    else:
        path_only = path

    path = resolve_path(path_only, concrete, non_concrete)

    operation_id = generate_operation_id(method.value, path)
    return operation_id
