"""Tests for docker helper methods."""

from pathlib import Path

from conftest import start_mongodb

from telephuzz.docker_helpers import write_to_container


def test_write_container(mongodb):
    """Test writing from one API container to another."""
    db1 = start_mongodb(27017, mongodb)
    db2 = start_mongodb(27018, mongodb)
    text = "test"
    path = "/test_write_container.txt"
    db1.exec_run(f'sh -c "echo \\"{text}\\" > {path}"')

    exit_code, output = db2.exec_run(f"test -e {path}")
    assert exit_code != 0, output

    write_to_container(db1, db2, Path(path))

    exit_code, output = db2.exec_run(f"test -e {path}")
    assert exit_code == 0, output

    db1.kill()
    db2.kill()
