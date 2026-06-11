"""Tests for docker helper methods."""

import subprocess
import tempfile
from pathlib import Path

from conftest import start_mongodb

from telephuzz.docker_helpers import (
    compose_down,
    compose_up,
    write_to_container,
    write_to_host,
)
from telephuzz.session.api import APIMongoDBDatabaseContainer


def test_write_host(mongodb):
    """Test writing from API container to host."""
    db1 = start_mongodb(27017, mongodb)
    with APIMongoDBDatabaseContainer(port=27017, db_container=db1) as _:
        text = "test"
        path = "/test_write_container.txt"
        db1.exec_run(f'sh -c "echo \\"{text}\\" > {path}"')

        exit_code, output = db1.exec_run(f"test -e {path}")
        assert exit_code == 0, output

        with tempfile.NamedTemporaryFile(mode="w+") as f:
            write_to_host(db1, "/test_write_container.txt", f.name)

            f.seek(0)
            assert f.read() == "test\n"


def test_write_container(mongodb):
    """Test writing from one API container to another."""
    db1 = start_mongodb(27017, mongodb)
    db2 = start_mongodb(27018, mongodb)

    with (
        APIMongoDBDatabaseContainer(port=27017, db_container=db1) as _1,
        APIMongoDBDatabaseContainer(port=27018, db_container=db2) as _2,
    ):
        text = "test"
        path = "/test_write_container.txt"
        db1.exec_run(f'sh -c "echo \\"{text}\\" > {path}"')

        exit_code, output = db2.exec_run(f"test -e {path}")
        assert exit_code != 0, output

        write_to_container(db1, db2, Path(path))

        exit_code, output = db2.exec_run(f"test -e {path}")
        assert exit_code == 0, output


def test_compose():
    """Test docker compose up and down methods."""
    compose_file = Path(__file__).parent / "testfiles" / "docker-compose.yml"
    project = "test_compose"

    compose_up(compose_path=compose_file, project=project)

    assert (
        project.encode()
        in subprocess.run(
            ["docker", "ps", "--filter", f"label=com.docker.compose.project={project}"],
            capture_output=True,
        ).stdout
    )

    compose_down(compose_path=compose_file, project=project)

    assert (
        project.encode()
        not in subprocess.run(
            ["docker", "ps", "--filter", f"label=com.docker.compose.project={project}"],
            capture_output=True,
        ).stdout
    )
