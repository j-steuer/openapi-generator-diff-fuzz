"""Tests for API classes."""

import tempfile
from pathlib import Path

import docker
import pytest
from docker.models.containers import Container

from telephuzz.session.api import APIH2DatabaseContainer, APIMongoDBDatabaseContainer


class TestH2:
    """Tests for H2."""

    def start_h2(self, port1: int, port2: int, image_name: str) -> Container:
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

    def test_init(self, h2: str):
        """Test initializing H2 Container."""
        db = self.start_h2(8082, 9092, h2)
        with APIH2DatabaseContainer(db_container=db) as db_container:
            assert db_container.db_container
            assert db_container.jar_path == Path("/opt/h2/h2.jar")

    def test_export_import(self, h2: str):
        """Unit test for H2 export and import methods."""
        db1 = self.start_h2(8082, 9092, h2)
        db2 = self.start_h2(8083, 9093, h2)

        # seed db1 with users
        create = """
        CREATE TABLE users (
        id INT PRIMARY KEY,
        name VARCHAR(255),
        email VARCHAR(255)
        );
        """

        insert = """
        INSERT INTO users (id, name, email)
        VALUES
        (1, 'Alice', 'alice@example.com'),
        (2, 'Bob', 'bob@example.com'),
        (3, 'Charlie', 'charlie@example.com');
        """

        db1.exec_run(f'sh -c "echo \\"{create}\\" > /tmp/command.sql"')
        db1.exec_run("""
        java -cp /opt/h2/h2.jar org.h2.tools.RunScript \
        -url jdbc:h2:/opt/h2/testdb \
        -user sa \
        -script /tmp/command.sql
        """)

        db1.exec_run(f'sh -c "echo \\"{insert}\\" > /tmp/command.sql"')
        db1.exec_run("""
        java -cp /opt/h2/h2.jar org.h2.tools.RunScript \
        -url jdbc:h2:/opt/h2/testdb \
        -user sa \
        -script /tmp/command.sql
        """)

        with (
            APIH2DatabaseContainer(db_container=db1) as db1_container,
            APIH2DatabaseContainer(db_container=db2) as db2_container,
        ):
            db1_container.export_db_state(Path("/export.sql"))

            # assert export.sql was created
            exit_code, output = db1.exec_run("cat /export.sql")
            assert exit_code == 0, output
            assert isinstance(output, bytes)
            assert "CREATE" in output.decode()
            assert "Alice" in output.decode()

            stream, _ = db1.get_archive("/export.sql")

            with tempfile.NamedTemporaryFile(
                mode="wb+", suffix=".sql", delete=True
            ) as temp_file:
                for chunk in stream:
                    temp_file.write(chunk)
                temp_file.seek(0)

                db2.put_archive("/", temp_file.read())
                db2.exec_run("mv /export.sql /import.sql")

            # assert import.sql exists
            exit_code, output = db2.exec_run("cat /import.sql")
            assert exit_code == 0, output

            db2_container.import_db_state(Path("/import.sql"))

            db2.exec_run('sh -c "echo \\"SELECT * FROM users\\" > /tmp/command.sql"')

            exit_code, output = db2.exec_run("""
            java -cp /opt/h2/h2.jar org.h2.tools.Shell \
            -url jdbc:h2:/opt/h2/testdb \
            -user sa \
            -sql "SELECT * FROM users"
            """)

            assert exit_code == 0, output

            assert isinstance(output, bytes)
            result_output = output.decode()

            assert "Alice" in result_output
            assert "alice@example.com" in result_output
            assert "Bob" in result_output
            assert "bob@example.com" in result_output
            assert "Charlie" in result_output
            assert "charlie@example.com" in result_output

    def test_get_state(self, h2: str):
        """Test obtaining the state of an H2 db."""
        db = self.start_h2(8082, 9092, h2)
        with APIH2DatabaseContainer(db_container=db) as db_container:
            db_container.get_state(Path("/state"))
            exit_code, output = db.exec_run("cat /state")
            assert exit_code == 0, output
            print(output)

    @pytest.mark.skip(reason="Needs postprocessing")
    def test_compare_state_identical(self, h2: str):
        """Test that diff file should be identical when dbs are."""
        db1 = self.start_h2(8082, 9092, h2)
        db2 = self.start_h2(8093, 9093, h2)
        with (
            APIH2DatabaseContainer(db_container=db1) as db1_container,
            APIH2DatabaseContainer(db_container=db2) as db2_container,
        ):
            db1_container.get_state(Path("/state"))
            exit_code, output1 = db1.exec_run("cat /state")
            assert exit_code == 0, output1

            db2_container.get_state(Path("/state"))
            exit_code, output2 = db2.exec_run("cat /state")
            assert exit_code == 0, output2

            assert output1 == output2


class TestMongoDB:
    """Tests for MongoDB."""

    def start_mongodb(self, port: int, image_name: str) -> Container:
        """Start a docker container with an MongoDB instance."""
        client = docker.from_env()
        db1 = client.containers.run(
            image_name,
            detach=True,
            ports={"27017/tcp": port},
        )
        return db1

    def test_init(self, mongodb: str):
        """Test initializing MongoDB container."""
        db = self.start_mongodb(27017, mongodb)
        with APIMongoDBDatabaseContainer(db_container=db) as db_container:
            assert db_container.db_container == db

    def test_export_import(self, mongodb: str):
        """Unit test for MongoDB export and import methods."""
        db1 = self.start_mongodb(27017, mongodb)
        db2 = self.start_mongodb(27018, mongodb)

        # seed db1 with users
        create = """
        db.createCollection("users")
        """

        insert = """
        db.users.insertOne({
        name: "Alice",
        age: 25,
        email: "alice@example.com"
        })
        """

        db1.exec_run(["mongosh", "--quiet", "--eval", create])
        db1.exec_run(["mongosh", "--quiet", "--eval", insert])

        with (
            APIMongoDBDatabaseContainer(db_container=db1) as db1_container,
            APIMongoDBDatabaseContainer(db_container=db2) as db2_container,
        ):
            db1_container.export_db_state(Path("/export"))

            # assert export.sql was created
            exit_code, output = db1.exec_run("test -d /export")
            assert exit_code == 0, output

            stream, _ = db1.get_archive("/export")

            with tempfile.NamedTemporaryFile(mode="wb+", delete=True) as temp_file:
                for chunk in stream:
                    temp_file.write(chunk)
                temp_file.seek(0)

                db2.put_archive("/", temp_file.read())
                db2.exec_run("mv /export /import")

            # assert import.sql exists
            exit_code, output = db2.exec_run("test -d /import")
            assert exit_code == 0, output

            db2_container.import_db_state(Path("/import"))

            exit_code, output = db2.exec_run(
                ["mongosh", "--quiet", "--eval", "db.users.find()"]
            )

            assert exit_code == 0, output

            assert isinstance(output, bytes)
            result_output = output.decode()

            assert "Alice" in result_output
            assert "alice@example.com" in result_output
