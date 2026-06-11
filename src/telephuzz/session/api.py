"""File for code relating to API containers."""

import ast
import time
from abc import ABC, abstractmethod
from pathlib import Path

from docker.models.containers import Container
from requests.models import CaseInsensitiveDict

# TODO implement postprocessing for nondeterministic columns


class APIContainer:
    """A container for a target API."""

    db_container: Container | None

    def __init__(self, port: int, db_container: Container | None = None):
        """Initialize the API container."""
        self.port = port
        self.db_container = db_container

    def __enter__(self):
        """Make mitmproxy container a context manager."""
        return self

    # TODO wait_until_ready

    def __exit__(self, exc_type, exc, tb):
        """Run close method when context ends."""
        self.close()

    def close(self) -> None:
        """Kill the container after context ends."""
        if self.db_container is None:
            return

        try:
            self.db_container.kill()
        finally:
            self.db_container.remove(force=True)
            self.db_container = None


class APIWithDatabaseContainer(ABC, APIContainer):
    """Abstract class for an API that uses a database system."""

    id: str
    registry: CaseInsensitiveDict = CaseInsensitiveDict()

    def __init_subclass__(cls, **kwargs):
        """Obtain subclass id for registry lookup."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "id"):
            APIWithDatabaseContainer.registry[cls.id] = cls

    @classmethod
    def from_id(cls, id_: str):
        """Obtain concrete client library based on id."""
        return cls.registry[id_.lower()]

    @abstractmethod
    def export_db_state(self, export_file: Path) -> None:
        """Export the current state of the DB to export_file."""
        raise NotImplementedError

    @abstractmethod
    def import_db_state(self, import_file: Path) -> None:
        """Import the new state of the DB from import_file."""
        raise NotImplementedError

    @abstractmethod
    def get_state(self, out: Path) -> None:
        """Write the state to a file that can be used for hashing and diff."""
        raise NotImplementedError


class APIH2DatabaseContainer(APIWithDatabaseContainer):
    """API Container class using H2 as database."""

    id = "H2"

    def __init__(
        self, port: int, db_container: Container, jar_path: Path | None = None
    ):
        """Determine path to H2 jar."""
        super().__init__(port=port, db_container=db_container)
        assert self.db_container

        if jar_path:
            self.jar_path = jar_path
        else:
            result = self.db_container.exec_run('find / -type f -name "h2.jar"').output
            assert isinstance(result, bytes), (
                f"Unexpected output for find command: {result}"
            )
            self.jar_path = Path(result.decode().rstrip())
        if not self.jar_path:
            raise ValueError("Could not find the jar path.")

    def _run_command(self, cmnd: str) -> str:
        """Run the provided command and return the output."""
        assert self.db_container

        # We use the -sql flag to pass the command directly to the Shell tool
        # and -silent to remove unnecessary header/footer info if desired.
        exit_code, output = self.db_container.exec_run(f"""
        java -cp {self.jar_path} org.h2.tools.Shell \
        -url jdbc:h2:/opt/h2/testdb \
        -user sa \
        -sql "{cmnd}"
        """)

        assert isinstance(output, bytes)

        if exit_code != 0:
            raise Exception(f"Query failed: {output.decode()}")

        return output.decode("utf-8")

    def export_db_state(self, export_file: Path) -> None:
        """Export the current state of the DB to export_file."""
        assert self.db_container
        cmnd = f"SCRIPT TO '{export_file}';"
        self._run_command(cmnd)

    def import_db_state(self, import_file: Path) -> None:
        """Import the new state of the DB from import_file."""
        assert self.db_container
        cmnd = f"RUNSCRIPT FROM '{import_file}';"
        self._run_command(cmnd)

    def get_state(self, out: Path) -> None:
        """Write the state to a file that can be used for hashing and diff."""
        assert self.db_container

        tables_string = self._run_command("SHOW TABLES;")
        # parse tables
        tables = []
        for table_row in tables_string.splitlines()[1:][:-1]:
            table_name = table_row[: table_row.find("|")].strip()
            tables.append(table_name)

        # write data to file
        with open(out, "w") as f:
            for table in tables:
                rows = self._run_command(f"SELECT * FROM {table};")
                f.write("".join(rows.splitlines(keepends=True)[:-1]))


class APIMongoDBDatabaseContainer(APIWithDatabaseContainer):
    """API Container class using MongoDB as database."""

    id = "MongoDB"

    def __enter__(self):
        """Verify MongoDB is running before returning."""
        super().__enter__()
        self.wait_until_ready()
        return self

    def wait_until_ready(self, timeout: int = 30) -> None:
        """Check if the MongoDB server is accepting connections."""
        assert self.db_container is not None

        start_time = time.time()
        while time.time() - start_time < timeout:
            # ping the admin database to check liveness
            exit_code, _ = self.db_container.exec_run(
                "mongosh --quiet --eval 'db.adminCommand(\"ping\")'"
            )

            if exit_code == 0:
                return

            time.sleep(1)

        raise TimeoutError("MongoDB container failed to reach 'ready' state in time.")

    def _run_command(self, cmnd: str) -> str:
        assert self.db_container is not None
        exit_code, output = self.db_container.exec_run(cmnd)
        assert exit_code == 0, output

        assert isinstance(output, bytes)
        return output.decode()

    def export_db_state(self, export_file: Path) -> None:
        """Export the current state of the DB to export_file."""
        str_command = f"mongodump --archive={export_file}"
        self._run_command(str_command)

    def import_db_state(self, import_file: Path) -> None:
        """Import the new state of the DB from import_file."""
        str_command = f"mongorestore --drop --archive={import_file}"
        self._run_command(str_command)

    def get_state(self, out: Path) -> None:
        """Write the state to a file that can be used for hashing and diff."""
        collections = ast.literal_eval(
            self._run_command("mongosh --quiet --eval db.getCollectionNames()")
        )
        for collection in collections:
            with open(out, "w") as f:
                find = f"db.{collection}.find({{}}, {{'_id': false}})"
                content = self._run_command(f'mongosh --quiet --eval "{find}"')
                f.write(content + "\n")


class APIMySQLDatabaseContainer(APIWithDatabaseContainer):
    """API container class using MySQL as database."""

    id = "MySQL"

    def _run_command(self, cmnd: str) -> str:
        assert self.db_container is not None
        exit_code, output = self.db_container.exec_run(cmnd)
        assert exit_code == 0, output

        assert isinstance(output, bytes)
        return output.decode()

    def export_db_state(self, export_file: Path) -> None:
        """Export the current state of the DB to export_file."""
        str_command = f"mysql mysqldump -u root -p --all-databases > {export_file}"
        self._run_command(str_command)

    def import_db_state(self, import_file: Path) -> None:
        """Import the new state of the DB from import_file."""
        str_command = f"cat {import_file} | mysql mysql -u root -p"
        self._run_command(str_command)

    def get_state(self, out: Path) -> None:
        """Write the state to a file that can be used for hashing and diff."""
        assert self.db_container

        tables_string = self._run_command("SHOW TABLES;")
        # parse tables
        tables = []
        for table_row in tables_string.splitlines()[1:][:-1]:
            table_name = table_row[: table_row.find("|")].strip()
            tables.append(table_name)

        # write data to file
        with open(out, "w") as f:
            for table in tables:
                rows = self._run_command(f"SELECT * FROM {table};")
                f.write("".join(rows.splitlines(keepends=True)[:-1]))
