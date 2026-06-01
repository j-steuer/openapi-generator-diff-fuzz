"""Tests for API classes."""

import tempfile
from pathlib import Path

import docker
from docker.models.containers import Container

from telephuzz.session.api import APIH2DatabaseContainer, APIMongoDBDatabaseContainer

FILL_COMMAND = """
            CREATE TABLE users1 (
            id INT PRIMARY KEY,
            name VARCHAR(255),
            email VARCHAR(255)
            );
                                      
            CREATE TABLE users2 (
            id INT PRIMARY KEY,
            name VARCHAR(255),
            email VARCHAR(255)
            );
                                      
            INSERT INTO users1 (id, name, email)
            VALUES
            (1, 'Alice', 'alice@example.com'),
            (2, 'Bob', 'bob@example.com');
                                      
            INSERT INTO users2 (id, name, email)
            VALUES
            (1, 'Charlie', 'charlie@example.com');
            """


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
            db_container._run_command(FILL_COMMAND)

            with tempfile.NamedTemporaryFile("w+") as f:
                db_container.get_state(Path(f.name))
                f.seek(0)
                result = f.read()

            assert "Alice" in result
            assert "alice@example.com" in result
            assert "Bob" in result
            assert "bob@example.com" in result
            assert "Charlie" in result
            assert "charlie@example.com" in result

    def test_compare_state_identical(self, h2: str):
        """Test that diff file should be identical when dbs are."""
        db1 = self.start_h2(8082, 9092, h2)
        db2 = self.start_h2(8093, 9093, h2)
        with (
            APIH2DatabaseContainer(db_container=db1) as db1_container,
            APIH2DatabaseContainer(db_container=db2) as db2_container,
        ):
            # empty DBs should be the same
            with tempfile.NamedTemporaryFile("w+") as f:
                db1_container.get_state(Path(f.name))
                f.seek(0)
                empty_result1 = f.read()

            with tempfile.NamedTemporaryFile("w+") as f:
                db2_container.get_state(Path(f.name))
                f.seek(0)
                empty_result2 = f.read()

            assert empty_result1 == empty_result2

            # identical DBs should be the same
            db1_container._run_command(FILL_COMMAND)
            db2_container._run_command(FILL_COMMAND)

            with tempfile.NamedTemporaryFile("w+") as f:
                db1_container.get_state(Path(f.name))
                f.seek(0)
                filled_result1 = f.read()

            with tempfile.NamedTemporaryFile("w+") as f:
                db2_container.get_state(Path(f.name))
                f.seek(0)
                filled_result2 = f.read()

            assert filled_result1 == filled_result2

    def test_compare_state_diff(self, h2: str):
        """Test that diff file should be different when dbs are."""
        db1 = self.start_h2(8082, 9092, h2)
        db2 = self.start_h2(8093, 9093, h2)
        with (
            APIH2DatabaseContainer(db_container=db1) as db1_container,
            APIH2DatabaseContainer(db_container=db2) as db2_container,
        ):
            db1_container._run_command(FILL_COMMAND)

            # should be different
            with tempfile.NamedTemporaryFile("w+") as f:
                db1_container.get_state(Path(f.name))
                f.seek(0)
                empty_result1 = f.read()

            with tempfile.NamedTemporaryFile("w+") as f:
                db2_container.get_state(Path(f.name))
                f.seek(0)
                empty_result2 = f.read()

            assert empty_result1 != empty_result2


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
