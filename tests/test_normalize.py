import json

from requests.structures import CaseInsensitiveDict

from telephuzz.evaluation.normalize import OpenAPINormalizer
from telephuzz.http_message import HTTPMethod, Request


def _request(body: dict) -> Request:
    """Create a JSON POST request."""
    return Request(
        method=HTTPMethod.POST,
        path="/users",
        query_parameters={},
        headers=CaseInsensitiveDict({"content-type": "application/json"}),
        body=json.dumps(body).encode(),
    )


def _spec(profile_schema: dict) -> dict:
    """Create an OpenAPI spec with a referenced nested profile."""
    return {
        "openapi": "3.0.3",
        "paths": {
            "/users": {
                "post": {
                    "requestBody": {
                        "$ref": "#/components/requestBodies/CreateUser",
                    }
                }
            }
        },
        "components": {
            "requestBodies": {
                "CreateUser": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/User"},
                        }
                    },
                }
            },
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "profile": {"$ref": "#/components/schemas/Profile"},
                    },
                },
                "Profile": {
                    "type": "object",
                    "properties": {
                        "created_at": profile_schema,
                    },
                },
            },
        },
    }


def test_normalize_datetime_with_nested_ref():
    """Datetime nested inside referenced schemas should be normalized."""
    spec = _spec({"type": "string", "format": "date-time"})
    normalizer = OpenAPINormalizer(spec)

    body = {"name": "John", "profile": {"created_at": "..."}}

    request1 = _request(body | {"profile": {"created_at": "2026-09-03T20:30:00Z"}})
    request2 = _request(body | {"profile": {"created_at": "2026-09-03T20:30:00+00:00"}})

    assert normalizer.normalize(request1) == normalizer.normalize(request2)


def test_normalize_only_when_schema_has_format():
    """Datetime-like strings should only be normalized when specified."""
    spec = _spec({"type": "string"})
    normalizer = OpenAPINormalizer(spec)

    request1 = _request(
        {"name": "John", "profile": {"created_at": "2026-09-03T20:30:00Z"}}
    )
    request2 = _request(
        {
            "name": "John",
            "profile": {"created_at": "2026-09-03T20:30:00+00:00"},
        }
    )

    assert normalizer.normalize(request1) != normalizer.normalize(request2)


def test_normalize_resolves_request_body_ref():
    """A requestBody referenced from components should be resolved."""
    spec = _spec({"type": "string", "format": "date-time"})
    normalizer = OpenAPINormalizer(spec)

    request1 = _request({"profile": {"created_at": "2026-09-03T20:30:00Z"}})
    request2 = _request({"profile": {"created_at": "2026-09-03T20:30:00+00:00"}})

    assert normalizer.normalize(request1) == normalizer.normalize(request2)
