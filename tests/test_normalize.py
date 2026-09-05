import json

from conftest import TEST_CONFIG_2_0_BASE_PATH
from requests.structures import CaseInsensitiveDict

from telephuzz.config import Config, get_config
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


def test_normalize_path():
    """Path encoding should be normalized."""
    Config.API_CONFIG_PATH = (
        TEST_CONFIG_2_0_BASE_PATH / "api_gestaohospital_config.yaml"
    )
    spec = get_config().spec
    normalizer = OpenAPINormalizer(spec)

    request1 = _request({})
    request2 = _request({})
    request1.path = (
        "/v1/hospitais/MultiMatch(values=%5B'2',%20'3'%5D)/pacientes/checkin"
    )
    request2.path = (
        "/v1/hospitais/MultiMatch%28values%3D%5B"
        "%272%27%2C%20%273%27%5D%29/pacientes/checkin"
    )

    assert normalizer.normalize(request1) == normalizer.normalize(request2)


def test_normalize_body_order():
    """Order of body elements should be normalized."""
    spec = _spec(
        {
            "type": "object",
            "properties": {
                "created_at": {"type": "string", "format": "date-time"},
                "updated_at": {"type": "string", "format": "date-time"},
            },
        }
    )
    normalizer = OpenAPINormalizer(spec)

    request1 = _request(
        {
            "profile": {
                "created_at": "2026-09-03T20:30:00Z",
                "updated_at": "2026-09-03T21:30:00Z",
            }
        }
    )
    request2 = _request(
        {
            "profile": {
                "updated_at": "2026-09-03T21:30:00Z",
                "created_at": "2026-09-03T20:30:00Z",
            }
        }
    )

    assert normalizer.normalize(request1).body == normalizer.normalize(request2).body
