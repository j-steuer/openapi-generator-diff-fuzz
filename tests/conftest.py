"""File for pytest fixtures."""

import json
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml  # type: ignore
from requests.structures import CaseInsensitiveDict

from telephuzz.http_message import HTTPMethod, Request


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
    """Fixture for dummy request if content is not relevant."""
    return Request(
        headers=CaseInsensitiveDict({"Test": ["test"]}),
        body=None,
        content_type=None,
        method=HTTPMethod.GET,
        path="dummytarget.org/test",
        path_parameters={},
        query_parameters={},
    )


# TODO come up with better testing fixture
@pytest.fixture
def api():
    """Fixture for tests needing an API running, runs at port 8000."""
    api_file = Path(__file__).resolve().parent / "testfiles" / "api.py"
    proc = subprocess.Popen(["fastapi", "run", api_file])

    yield "http://host.docker.internal:8000"

    proc.terminate()
