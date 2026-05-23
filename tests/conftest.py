"""File for pytest fixtures."""

import json
import subprocess
import tempfile
import time
from pathlib import Path

import pytest
import requests
import yaml  # type: ignore
from requests.structures import CaseInsensitiveDict

from telephuzz.http_message import HTTPMethod, Request, Response


@pytest.fixture
def basic_oas_json():
    """Fixture for a simple OAS file in JSON."""
    content = json.loads("""
        {
    "openapi": "3.0.0",
    "info": {
        "title": "Simple API",
        "version": "1.0.0"
    },
    "paths": {
        "/items": {
        "get": {
            "operationId": "listItems",
            "responses": {
            "200": { "description": "OK" }
            }
        },
        "post": {
            "responses": {
            "201": { "description": "Created" }
            }
        }
        },
        "/items/{id}": {
        "parameters": [
            {
            "name": "id",
            "in": "path",
            "required": true,
            "schema": { "type": "string" },
            "responses": {
                "200": { "description": "Patched" }
            }
            }
        ],
        "get": {
            "responses": {
            "200": { "description": "OK" }
            }
        },
        "put": {
            "operationId": "updateItem",
            "responses": {
            "200": { "description": "Updated" }
            }
        },
        "delete": {
            "responses": {
            "204": { "description": "Deleted" }
            }
        },
        "patch": {
            "responses": {
            "200": { "description": "Patched" }
            }
        },
        "head": {
            "responses": {
            "200": { "description": "OK" }
            }
        },
        "options": {
            "responses": {
            "204": { "description": "No Content" }
            }
        }
        }
    }
    }
    """)

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=True) as f:
        json.dump(content, f)
        f.flush()
        f.seek(0)
        yield f


@pytest.fixture
def basic_oas_yaml():
    """Fixture for a simple OAS file in YAML."""
    content = yaml.safe_load("""
    openapi: 3.0.0
    info:
        title: Simple API
        version: 1.0.0

    paths:
        /items:
            get:
                operationId: listItems
                responses:
                    "200":
                        description: OK
            post:
                responses:
                    "201":
                        description: Created

        /items/{id}:
            parameters:
                -   name: id
                    in: path
                    required: true
                    schema:
                        type: string

            get:
                responses:
                    "200":
                        description: OK

            put:
                operationId: updateItem
                responses:
                    "200":
                        description: Updated

            delete:
                responses:
                    "204":
                        description: Deleted

            patch:
                responses:
                    "200":
                        description: Patched

            head:
                responses:
                    "200":
                        description: OK

            options:
                responses:
                    "204":
                        description: No Content
        """)

    with tempfile.NamedTemporaryFile(mode="w+", suffix=".yaml", delete=True) as f:
        yaml.safe_dump(content, f)
        f.flush()
        f.seek(0)
        yield f


@pytest.fixture
def basic_request():
    """Fixture for dummy request."""
    return Request(
        headers=CaseInsensitiveDict({"Test": ["test"]}),
        body=None,
        method=HTTPMethod.GET,
        path="dummytarget.org/test",
        query_parameters={},
    )


@pytest.fixture
def basic_response():
    """Fixture for dummy response."""
    return Response(
        headers=CaseInsensitiveDict({"Test": ["test"]}), body=None, status=404, text=""
    )


@pytest.fixture(scope="session")
def api(request):
    """Run a test API for this test."""
    variant = getattr(request, "param", "plain")

    filename = {
        "plain": "api.py",
        "auth": "api_oauth.py",
    }[variant]

    api_file = Path(__file__).resolve().parent / "testfiles" / filename

    proc = subprocess.Popen(["fastapi", "run", api_file])

    # wait for startup
    for _ in range(30):
        try:
            r = requests.get("http://localhost:8000/openapi.json")
            if r.status_code == 200:
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(0.5)

    yield "http://host.docker.internal:8000"

    proc.terminate()
