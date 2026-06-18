"""File for pytest fixtures."""

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Protocol, runtime_checkable
from unittest.mock import Mock

import docker
import pytest
import requests
import yaml  # type: ignore
from docker.errors import ImageNotFound
from docker.models.containers import Container
from requests.structures import CaseInsensitiveDict

from telephuzz.config import Config
from telephuzz.http_message import HTTPMethod, Request, Response
from telephuzz.session.api import APIContainer, APIWithDatabaseContainer
from telephuzz.session.client_library import ClientLibraryContainer

TEST_CONFIG_PATH = Path(__file__).parent / "testfiles" / "config.yaml"


@runtime_checkable
class PrefillMethod(Protocol):
    """Definition of prefill callable fixture."""

    def __call__(
        self,
        port1: int,
        port2: int,
        insert: str | None = None,
    ) -> Container:
        """Call method."""
        ...


def start_h2(port1: int, port2: int, image_name: str) -> Container:
    """Start a docker container with an H2 instance."""
    client = docker.from_env()
    db1 = client.containers.run(
        image_name,
        detach=True,
        ports={
            "8082/tcp": ("127.0.0.1", port1),
            "9092/tcp": ("127.0.0.1", port2),
        },
    )
    return db1


def start_mongodb(port: int, image_name: str) -> Container:
    """Start a docker container with an MongoDB instance."""
    client = docker.from_env()
    db1 = client.containers.run(
        image_name,
        detach=True,
        ports={"27017/tcp": port},
    )
    return db1


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


@pytest.fixture(autouse=True)
def setup():
    """Redirect config path to test config."""
    original = Config.CONFIG_PATH
    Config.CONFIG_PATH = TEST_CONFIG_PATH
    yield
    Config.CONFIG_PATH = original

    shutil.rmtree("/tmp/logs/telephuzz", ignore_errors=True)


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


@pytest.fixture()
def mock_client():
    """Mock client library class."""
    mock_client = Mock(spec=ClientLibraryContainer)
    mock_client.mock_body = "MOCK_BODY"
    mock_client.send.return_value = Response(
        headers=CaseInsensitiveDict(),
        body=mock_client.mock_body,
        status=200,
        text=None,
    )
    mock_client.id = "MOCK_ID"

    return mock_client


@pytest.fixture()
def mock_api_no_db():
    """Mock API without a DB."""
    mock_api = Mock(spec=APIContainer)
    mock_api.db_container = None
    return mock_api


@pytest.fixture()
def mock_api_with_db():
    """Mock API with DB."""
    mock_api = Mock(spec=APIWithDatabaseContainer)
    mock_api.db_container = Mock(spec=Container)
    return mock_api


@pytest.fixture()
def prefilled_h2(h2) -> PrefillMethod:
    """Create an H2 db instance with a default table and optional content.

    Default table is users(id INT PRIMARY KEY, name VARCHAR(255), email VARCHAR(255))
    """

    def get_h2(port1: int, port2: int, insert: str | None = None) -> Container:
        db = start_h2(port1, port2, h2)

        create = """
        CREATE TABLE users (
        id INT PRIMARY KEY,
        name VARCHAR(255),
        email VARCHAR(255)
        );
        """

        db.exec_run(f'sh -c "echo \\"{create}\\" > /tmp/command.sql"')
        db.exec_run("""
        java -cp /opt/h2/h2.jar org.h2.tools.RunScript \
        -url jdbc:h2:/opt/h2/testdb \
        -user sa \
        -script /tmp/command.sql
        """)

        if insert is not None:
            db.exec_run(f'sh -c "echo \\"{insert}\\" > /tmp/command.sql"')
            db.exec_run("""
            java -cp /opt/h2/h2.jar org.h2.tools.RunScript \
            -url jdbc:h2:/opt/h2/testdb \
            -user sa \
            -script /tmp/command.sql
            """)

        return db

    return get_h2
