"""Normalization of HTTP requests according to an OpenAPI specification."""

import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote

from telephuzz.http_message import Request
from telephuzz.openapi_helpers import (
    get_request_body_schema,
    resolve_path,
    resolve_schema,
)


class OpenAPINormalizer:
    """Normalize request bodies according to an OpenAPI specification.

    The normalizer is intended to be instantiated for one OpenAPI spec and
    reused for multiple requests.
    """

    def __init__(self, spec: dict):
        """Initialize the normalizer with an OpenAPI specification."""
        self.spec = spec

        # The evaluator/normalizer is used with one spec for its entire
        # lifetime, so caching the serialized representation and operation
        # lookup avoids repeatedly traversing the spec.
        self._spec_json = json.dumps(spec, sort_keys=True)
        self._operation_cache: dict[tuple[str, str], dict] = {}
        self._schema_cache: dict[tuple[str, str], dict | None] = {}

    def normalize(self, request: Request) -> Request:
        """Return a normalized copy of a request."""
        normalized = deepcopy(request)

        normalized.path = self._normalize_path(normalized.path)

        if normalized.body is None:
            return normalized

        if not self._is_json_request(normalized):
            return normalized

        try:
            body = json.loads(normalized.body)
        except (TypeError, json.JSONDecodeError):
            return normalized

        schema = self._get_request_body_schema(normalized)

        if schema is None:
            return normalized

        normalized_body = self._normalize_value(body, schema)

        normalized.body = json.dumps(
            normalized_body,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()

        return normalized

    def _normalize_path(self, path: str) -> str:
        """Normalize the path."""
        return unquote(path)

    def _get_operation(self, request: Request) -> dict:
        """Find the OpenAPI operation for a request."""
        key = (request.method.value, request.path)

        if key in self._operation_cache:
            return self._operation_cache[key]

        resolved_path = resolve_path(request.path, self._spec_json)

        path_item = self.spec.get("paths", {}).get(resolved_path)
        if not isinstance(path_item, dict):
            raise ValueError(
                f"Path {resolved_path!r} not found in OpenAPI specification."
            )

        operation = path_item.get(request.method.value.lower())

        if not isinstance(operation, dict):
            raise ValueError(
                f"Operation at {request.method.value} {request.path} not found."
            )

        self._operation_cache[key] = operation
        return operation

    def _get_request_body_schema(self, request: Request) -> dict | None:
        """Find and resolve the request body schema for a request."""
        key = (request.method.value, request.path)

        if key in self._schema_cache:
            return self._schema_cache[key]

        operation = self._get_operation(request)
        schema = get_request_body_schema(self.spec, operation)

        if schema is None:
            self._schema_cache[key] = None
            return None

        resolved = resolve_schema(self.spec, schema)
        self._schema_cache[key] = resolved

        return resolved

    @staticmethod
    def _is_json_request(request: Request) -> bool:
        """Return whether the request contains JSON."""
        content_type = request.headers.get("content-type")

        if content_type is None:
            return False

        # Ignore parameters such as:
        # application/json; charset=utf-8
        return content_type.split(";", 1)[0].strip().lower() == "application/json"

    def _normalize_value(self, value: Any, schema: dict) -> Any:
        """Normalize a JSON value according to its OpenAPI schema."""
        schema = resolve_schema(self.spec, schema)

        if self._is_datetime_schema(schema, value):
            return self._normalize_datetime(value)

        schema_type = schema.get("type")

        if schema_type == "object" or "properties" in schema:
            return self._normalize_object(value, schema)

        if schema_type == "array":
            return self._normalize_array(value, schema)

        return value

    def _normalize_object(self, value: Any, schema: dict) -> Any:
        """Normalize the properties of an object."""
        if not isinstance(value, dict):
            return value

        properties = schema.get("properties", {})

        if not isinstance(properties, dict):
            return value

        normalized = dict(value)

        for name, property_schema in properties.items():
            if name not in normalized:
                continue

            if not isinstance(property_schema, dict):
                continue

            normalized[name] = self._normalize_value(
                normalized[name],
                property_schema,
            )

        return normalized

    def _normalize_array(self, value: Any, schema: dict) -> Any:
        """Normalize array items according to their item schema."""
        if not isinstance(value, list):
            return value

        item_schema = schema.get("items")

        if not isinstance(item_schema, dict):
            return value

        return [self._normalize_value(item, item_schema) for item in value]

    @staticmethod
    def _is_datetime_schema(schema: dict, value: Any) -> bool:
        """Return whether a value uses the OpenAPI date-time format."""
        return (
            schema.get("type") == "string"
            and schema.get("format") == "date-time"
            and isinstance(value, str)
        )

    @staticmethod
    def _normalize_datetime(value: str) -> str:
        """Normalize an ISO date-time value to UTC."""
        # datetime.fromisoformat() accepts "+00:00" but historically did not
        # accept "Z" on all supported Python versions.
        if value.endswith("Z"):
            value = f"{value[:-1]}+00:00"

        parsed = datetime.fromisoformat(value)

        # OpenAPI date-time values should contain timezone information.
        # Preserve invalid/unaware values rather than inventing a timezone.
        if parsed.tzinfo is None:
            return value

        return parsed.astimezone(timezone.utc).isoformat()
