"""File for pytest fixtures."""

import json
import logging
import os
import shutil
import tempfile
import time
from copy import deepcopy
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

import telephuzz.config as cfg
from telephuzz.config import Config
from telephuzz.constants import BASE_PATH, SPEC_PATH
from telephuzz.http_message import HTTPMethod, Request
from telephuzz.session.api import APIContainer, APIWithDatabaseContainer

TESTFILES_PATH = BASE_PATH / "tests" / "testfiles"
TEST_CONFIG_BASE_PATH = TESTFILES_PATH / "configs"
TEST_API_CONFIG_PATH = TESTFILES_PATH / "api_config.yaml"

disable_loggers = ["urllib3.connectionpool", "docker.utils.config"]


def pytest_configure():
    for logger_name in disable_loggers:
        logger = logging.getLogger(logger_name)
        logger.disabled = True


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
def client_generator():
    """Generate clients libraries for testing purposes.

    For instance, make_client_class(BasicClient)
    will generate BasicClient1, BasicClient2 and BasicClient3 classes
    with ids basicclient1, basicclient2, basicclient3.
    """

    def make_client_classes(base: type, amount: int = 3) -> list[type]:
        types = []
        for i in range(amount):
            base_name = f"{base.__name__}{i + 1}"
            types.append(type(base_name, (base,), {"id": base_name.lower()}))

        return types

    return make_client_classes


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
    """Basic setup for all tests."""
    # clear spec
    if SPEC_PATH.exists():
        os.remove(SPEC_PATH)

    # clear logs
    shutil.rmtree("/tmp/logs/telephuzz", ignore_errors=True)

    original = Config.API_CONFIG_PATH
    Config.API_CONFIG_PATH = TEST_API_CONFIG_PATH

    # make config regenerate for each tes
    cfg._config = None
    yield
    Config.API_CONFIG_PATH = original


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
def spec_factory():
    """Create a minimal OpenAPI spec."""

    base_spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "Test API",
            "version": "1.0.0",
        },
        "servers": [{"url": "https://api.example.com"}],
        "paths": {},
    }

    def _factory(**overrides):
        spec = deepcopy(base_spec)
        spec.update(overrides)
        return spec

    return _factory


@pytest.fixture(scope="session")
def api():
    """Run a test API for this test."""
    dockerfiles = Path(__file__).resolve().parent / "testfiles" / "dockerfiles"

    client = docker.from_env()

    client.images.build(
        path=str(dockerfiles), dockerfile="api.dockerfile", tag="api_fixture"
    )

    network_name = "api_fixture"
    network = client.networks.create(network_name)

    container = client.containers.run(
        image="api_fixture",
        detach=True,
        ports={
            "8000/tcp": 8011,
        },
        name="api",
        remove=True,
        network=network.name,
    )

    # wait for startup
    for _ in range(30):
        try:
            r = requests.get("http://localhost:8011/openapi.json")
            if r.status_code == 200:
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(0.5)

    yield network, "http://api:8000"

    try:
        container.kill()
    except Exception:
        pass

    try:
        network.remove()
    except Exception:
        pass


@pytest.fixture(scope="session")
def api_oauth():
    """Run a test API for this test."""
    dockerfiles = Path(__file__).resolve().parent / "testfiles" / "dockerfiles"

    client = docker.from_env()

    client.images.build(
        path=str(dockerfiles),
        dockerfile="api_oauth.dockerfile",
        tag="api_oauth_fixture",
    )

    network_name = "api_oauth_fixture"
    network = client.networks.create(network_name)

    container = client.containers.run(
        image="api_oauth_fixture",
        detach=True,
        ports={
            "8001/tcp": 8001,
        },
        name="api_oauth",
        remove=True,
        network=network.name,
    )

    # wait for startup
    for _ in range(30):
        try:
            r = requests.get("http://localhost:8001/openapi.json")
            if r.status_code == 200:
                break
        except requests.exceptions.ConnectionError:
            pass
        time.sleep(0.5)

    yield network, "http://api_oauth:8001"

    container.kill()
    network.remove()


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
