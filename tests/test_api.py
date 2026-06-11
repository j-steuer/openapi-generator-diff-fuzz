"""Tests for API classes."""

import tempfile
from pathlib import Path

import docker
import pytest
from conftest import start_mongodb as sb
from docker.models.containers import Container

from telephuzz.session.api import (
    APIH2DatabaseContainer,
    APIMongoDBDatabaseContainer,
    APIMySQLDatabaseContainer,
    APIWithDatabaseContainer,
)

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


def test_from_id():
    """Test obtaining the database class from id."""
    h2 = APIWithDatabaseContainer.from_id("h2")
    assert h2 == APIH2DatabaseContainer


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
        with APIH2DatabaseContainer(port=8082, db_container=db) as db_container:
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
            APIH2DatabaseContainer(port=8082, db_container=db1) as db1_container,
            APIH2DatabaseContainer(port=8083, db_container=db2) as db2_container,
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
        with APIH2DatabaseContainer(port=8082, db_container=db) as db_container:
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
            APIH2DatabaseContainer(port=8082, db_container=db1) as db1_container,
            APIH2DatabaseContainer(port=8083, db_container=db2) as db2_container,
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
            APIH2DatabaseContainer(port=8082, db_container=db1) as db1_container,
            APIH2DatabaseContainer(port=8083, db_container=db2) as db2_container,
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

    CREATE_COMMAND = """
        db.createCollection("users")
        """
    INSERT_COMMAND = """
        db.users.insertOne({
        name: "Alice",
        age: 25,
        email: "alice@example.com"
        })
        """

    def start_mongodb(self, port: int, image_name: str) -> Container:
        """Start a docker container with an MongoDB instance."""
        return sb(port, image_name)

    def test_init(self, mongodb: str):
        """Test initializing MongoDB container."""
        db = self.start_mongodb(27017, mongodb)
        with APIMongoDBDatabaseContainer(port=27017, db_container=db) as db_container:
            assert db_container.db_container == db

    def test_export_import(self, mongodb: str):
        """Unit test for MongoDB export and import methods."""
        db1 = self.start_mongodb(27017, mongodb)
        db2 = self.start_mongodb(27018, mongodb)

        with (
            APIMongoDBDatabaseContainer(port=27017, db_container=db1) as db1_container,
            APIMongoDBDatabaseContainer(port=27018, db_container=db2) as db2_container,
        ):
            exit_code, output = db1.exec_run(
                ["mongosh", "--quiet", "--eval", self.CREATE_COMMAND]
            )
            assert exit_code == 0, output
            exit_code, output = db1.exec_run(
                ["mongosh", "--quiet", "--eval", self.INSERT_COMMAND]
            )
            assert exit_code == 0, output
            db1_container.export_db_state(Path("/export"))

            # assert export was created
            exit_code, output = db1.exec_run("test -e /export")
            assert exit_code == 0, output

            stream, _ = db1.get_archive("/export")

            with tempfile.NamedTemporaryFile(mode="wb+", delete=True) as temp_file:
                for chunk in stream:
                    temp_file.write(chunk)
                temp_file.seek(0)

                db2.put_archive("/", temp_file.read())
                exit_code, output = db2.exec_run("mv /export /import")
                assert exit_code == 0, output

            # assert import.sql exists
            exit_code, output = db2.exec_run("test -e /import")
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

    def test_get_state(self, mongodb: str):
        """Test obtaining the state."""
        db = self.start_mongodb(27017, mongodb)
        # seed db with users

        with APIMongoDBDatabaseContainer(port=27017, db_container=db) as db_container:
            db.exec_run(["mongosh", "--quiet", "--eval", self.CREATE_COMMAND])
            db.exec_run(["mongosh", "--quiet", "--eval", self.INSERT_COMMAND])

            with tempfile.NamedTemporaryFile("w+") as f:
                db_container.get_state(Path(f.name))
                f.seek(0)
                content = f.read()

            assert "Alice" in content
            assert "alice@example.com" in content
            assert "_id" not in content

    def test_compare_state_identical(self, mongodb: str):
        """Test that diff file should be identical when dbs are."""
        db1 = self.start_mongodb(27017, mongodb)
        db2 = self.start_mongodb(27018, mongodb)
        with (
            APIMongoDBDatabaseContainer(port=27017, db_container=db1) as db1_container,
            APIMongoDBDatabaseContainer(port=27018, db_container=db2) as db2_container,
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
            db1.exec_run(["mongosh", "--quiet", "--eval", self.CREATE_COMMAND])
            db1.exec_run(["mongosh", "--quiet", "--eval", self.INSERT_COMMAND])
            db2.exec_run(["mongosh", "--quiet", "--eval", self.CREATE_COMMAND])
            db2.exec_run(["mongosh", "--quiet", "--eval", self.INSERT_COMMAND])
            with tempfile.NamedTemporaryFile("w+") as f:
                db1_container.get_state(Path(f.name))
                f.seek(0)
                filled_result1 = f.read()

            with tempfile.NamedTemporaryFile("w+") as f:
                db2_container.get_state(Path(f.name))
                f.seek(0)
                filled_result2 = f.read()

            assert filled_result1 == filled_result2

    def test_compare_state_diff(self, mongodb: str):
        """Test that diff file should be different when dbs are."""
        db1 = self.start_mongodb(27017, mongodb)
        db2 = self.start_mongodb(27018, mongodb)
        with (
            APIMongoDBDatabaseContainer(port=27017, db_container=db1) as db1_container,
            APIMongoDBDatabaseContainer(port=27018, db_container=db2) as db2_container,
        ):
            db1.exec_run(["mongosh", "--quiet", "--eval", self.CREATE_COMMAND])
            db1.exec_run(["mongosh", "--quiet", "--eval", self.INSERT_COMMAND])

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


class TestMySQL:
    """Test MySQL container class."""

    IMAGE = "mysql:8.0"

    def start_mysql(self, port: int) -> Container:
        """Start a MySQL instance."""
        client = docker.from_env()

        container = client.containers.run(
            self.IMAGE,
            detach=True,
            environment={"MYSQL_ROOT_PASSWORD": "my-secret-pw"},
            ports={"3306/tcp": port},
        )

        return container

    def test_init(self):
        """Test initializing MongoDB container."""
        db = self.start_mysql(3306)
        with APIMySQLDatabaseContainer(port=3306, db_container=db) as db_container:
            assert db_container.db_container == db

    @pytest.mark.skip(reason="Fix")
    def test_export_import(self):
        """Unit test for MongoDB export and import methods."""
        db1 = self.start_mysql(3306)
        db2 = self.start_mysql(3307)

        with (
            APIMySQLDatabaseContainer(port=3306, db_container=db1) as db1_container,
            APIMySQLDatabaseContainer(port=3307, db_container=db2) as db2_container,
        ):
            exit_code, output = db1.exec_run(
                [
                    "mysql",  # MySQL client
                    "-uroot",  # username
                    "-pmy-secret-pw",  # password (no space after -p)
                    "-e",  # execute command
                    FILL_COMMAND,  # SQL command
                ]
            )
            assert exit_code == 0, output
            db1_container.export_db_state(Path("/export"))

            # assert export was created
            exit_code, output = db1.exec_run("test -e /export")
            assert exit_code == 0, output

            stream, _ = db1.get_archive("/export")

            with tempfile.NamedTemporaryFile(mode="wb+", delete=True) as temp_file:
                for chunk in stream:
                    temp_file.write(chunk)
                temp_file.seek(0)

                db2.put_archive("/", temp_file.read())
                exit_code, output = db2.exec_run("mv /export /import")
                assert exit_code == 0, output

            # assert import.sql exists
            exit_code, output = db2.exec_run("test -e /import")
            assert exit_code == 0, output

            db2_container.import_db_state(Path("/import"))

            assert isinstance(output, bytes)
            result_output = output.decode()

            assert "Alice" in result_output
            assert "alice@example.com" in result_output
