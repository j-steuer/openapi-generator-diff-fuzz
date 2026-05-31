"""File for pytest fixtures."""

import json
import subprocess
import tempfile
import time
from pathlib import Path

import docker
import pytest
import requests
import yaml  # type: ignore
from docker.errors import ImageNotFound
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
def api():
    """Run a test API for this test."""
    api_file = Path(__file__).resolve().parent / "testfiles" / "api.py"

    proc = subprocess.Popen(["fastapi", "run", api_file, "--port", "8000"])

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


@pytest.fixture(scope="session")
def api_oauth():
    """Run a test API for this test."""
    api_file = Path(__file__).resolve().parent / "testfiles" / "api_oauth.py"

    proc = subprocess.Popen(["fastapi", "run", api_file, "--port", "8001"])

    # wait for startup
    for _ in range(30):
        try:
            r = requests.get("http://localhost:8001/openapi.json")
            if r.status_code == 200:
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(0.5)

    yield "http://host.docker.internal:8001"

    proc.terminate()


@pytest.fixture()
def h2():
    """Build base h2 image if not already present."""
    client = docker.from_env()
    h2 = "telephuzz:h2"

    try:
        client.images.get(h2)
    except ImageNotFound:
        path = str(Path(__file__).resolve().parent / "testfiles" / "dockerfiles")
        client.images.build(path=path, dockerfile="h2.dockerfile", tag=h2)

    yield h2


@pytest.fixture()
def mongodb():
    """Build base MongoDB image if not already present."""
    client = docker.from_env()
    mongodb = "telephuzz:mongodb"

    try:
        client.images.get(mongodb)
    except ImageNotFound:
        path = str(Path(__file__).resolve().parent / "testfiles" / "dockerfiles")
        client.images.build(path=path, dockerfile="mongodb.dockerfile", tag=mongodb)

    yield mongodb
