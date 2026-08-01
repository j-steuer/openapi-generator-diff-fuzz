"""Helper methods for reading and processing an OpenAPI spec."""

import json
from functools import cache
from pathlib import Path
from typing import Any, cast
from urllib.parse import ParseResult, unquote, urlparse

import yaml  # type: ignore

from telephuzz.http_message import HTTPMethod
from telephuzz.operation_ids import generate_operation_id

DEFAULT_VERSION = "0.0.0"
RESTRICTED_MEDIA_TYPES = {"application/xml", "application/x-www-form-urlencoded"}


def preprocess_oas(oas: Path, output_path: Path | None = None) -> dict | None:
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

    # set version to simple constant to avoid format issues if used by a generator
    info = spec.get("info")
    if info is not None:
        if "version" in info:
            info["version"] = DEFAULT_VERSION

    for path, methods in spec.get("paths", {}).items():
        assert isinstance(methods, dict), "Methods were not loaded as a dict"
        methods = cast(dict[str, dict], methods)
        for method, operation in methods.items():
            try:
                HTTPMethod(method)
            except ValueError:
                # ignore non-method keys like parameters
                continue

            request_body = operation.get("requestBody")
            if isinstance(request_body, dict):
                content = request_body.get("content")
                if isinstance(content, dict):
                    # remove restricted media types if it does not leave content empty
                    if any(
                        media
                        for media in content
                        if media not in RESTRICTED_MEDIA_TYPES
                    ):
                        for media_type in RESTRICTED_MEDIA_TYPES:
                            content.pop(media_type, None)

                    if not content:
                        raise ValueError(
                            f"Content of {path} has no supported media types."
                        )

            operation["operationId"] = generate_operation_id(method, path)
    if output_path:
        with open(output_path, "w") as f:
            if output_path.suffix == ".json":
                json.dump(spec, f)
            elif output_path.suffix == ".yaml":
                yaml.safe_dump(spec, f)

    return spec


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


def get_version(spec: dict) -> str:
    try:
        return spec.get("openapi") or spec["swagger"]
    except KeyError as e:
        raise ValueError(
            "Provided spec is invalid, does not contain version information."
        ) from e


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
def _search_operation(spec: str, method: HTTPMethod, path: str) -> dict:
    """Search operation in spec."""
    operation_id = resolve_request_id(method, path, spec)
    operation = find_operation(json.loads(spec), operation_id)

    if operation is None:
        raise ValueError(f"Operation at {method} {path} not found.")

    assert isinstance(operation, dict)
    return operation


@cache
def get_args(spec: str, method: HTTPMethod, path: str) -> dict:
    """Obtain a list of arguments for the given operation id.

    Spec must be passed as string using json.dumps to enable caching.
    Returns "enum" as type if spec defines an enum.
    """
    # search operation id
    operation = _search_operation(spec, method, path)

    args = dict()
    if "requestBody" in operation:
        # get request body
        content = operation["requestBody"]["content"]
        ref = set(_find_all(content, "$ref"))
        if ref:
            assert len(ref) == 1
            ref = ref.pop()
            assert isinstance(ref, str)
            args["requestBody"] = ref[ref.rfind("/") + 1 :]
        else:
            schemas = _find_all(content, "schema")
            assert len(schemas) == 1
            schema = schemas.pop()
            args["requestBody"] = schema["type"]
    if "parameters" in operation:
        args.update(
            {
                p["name"]: p["schema"]["type"] if "enum" not in p["schema"] else "enum"
                for p in operation["parameters"]
            }
        )

    return args


@cache
def get_content_type(spec: str, method: HTTPMethod, path: str) -> str | None:
    """Get content tpy eof operation if available"""
    operation = _search_operation(spec, method, path)

    if "requestBody" not in operation:
        return None

    return list(operation["requestBody"]["content"].keys())[0]


def get_api_url_path(spec: dict) -> str:
    """Obtain the base path of the API."""
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


@cache
def extract_path_variable_types(spec_json: str, path: str) -> dict[str, str]:
    """Given an OpenAPI spec and an operation id, get the type of all path variables."""
    spec: dict = json.loads(spec_json)
    paths: dict = spec.get("paths", {})
    path_item: dict = paths[path]

    path_level_params = path_item.get("parameters", [])

    for method, operation in path_item.items():
        if method == "parameters" or not isinstance(operation, dict):
            continue

        result: dict[str, str] = {}

        # Operation-level parameters override path-level ones.
        params = path_level_params + operation.get("parameters", [])

        for param in params:
            if param.get("in") != "path":
                continue

            schema = param.get("schema", {})
            result[param["name"]] = schema.get("type", "string")

        return result

    raise KeyError(f"Path {path!r} not found")


def resolve_path(path: str, spec_json: str) -> str:
    """
    Resolve an incoming API path to:
    1. Exact match in concrete paths, or
    2. Best match among non-concrete paths, or
    3. Raise error if no match
    """

    path = _path_without_query(path)

    concrete_paths, non_concrete_paths = extract_paths(spec_json)

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


def _path_without_query(path: str) -> str:
    """Strip the query parameters from a path"""
    if "?" in path:
        return path[: path.find("?")]
    return path


def resolve_request_id(method: HTTPMethod, path: str, spec_str: str) -> str:
    operation_id = generate_operation_id(method.value, path)

    path_only = _path_without_query(path)

    path = resolve_path(path_only, spec_str)

    operation_id = generate_operation_id(method.value, path)
    return operation_id


def extract_path_parameters(template: str, path: str) -> dict[str, Any]:
    """Extract path parameters from a concrete path."""
    template_parts = template.strip("/").split("/")
    path_parts = path.strip("/").split("/")

    if len(template_parts) != len(path_parts):
        raise ValueError("Template and path have different numbers of segments.")

    params = {}

    for template_part, path_part in zip(template_parts, path_parts, strict=False):
        if template_part.startswith("{") and template_part.endswith("}"):
            name = template_part[1:-1]
            params[name] = unquote(path_part)
        elif template_part != path_part:
            raise ValueError(
                f"Static path segment mismatch: "
                f"expected '{template_part}', got '{path_part}'."
            )

    return params


def build_operation_lookup(spec: dict) -> dict[tuple[str, str], dict[str, Any]]:
    """Build a lookup index for operations keyed by (method, path)."""
    lookup: dict[tuple[str, str], dict[str, Any]] = {}

    for path, methods in spec.get("paths", {}).items():
        if not isinstance(methods, dict):
            continue

        for method, operation in methods.items():
            if not isinstance(operation, dict):
                continue

            try:
                HTTPMethod(method)
            except ValueError:
                continue

            normalized_method = method.lower()
            operation_id = operation.get("operationId")

            tags = operation.get("tags")
            tag: str | None = None
            if isinstance(tags, list) and tags:
                tag = tags[0]
            elif isinstance(tags, str):
                tag = tags

            lookup[(normalized_method, path)] = {
                "method": normalized_method,
                "path": path,
                "operation_id": operation_id,
                "tag": tag,
            }

    return lookup
