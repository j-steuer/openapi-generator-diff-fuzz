"""File for code relating to API containers."""

from abc import ABC, abstractmethod
from pathlib import Path

from docker.models.containers import Container


class APIContainer:
    """A container for a target API."""

    db_container: Container | None

    def __init__(self, db_container: Container):
        """Initialize the API container."""
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

    @abstractmethod
    def export_db_state(self, export_file: Path) -> None:
        """Export the current state of the DB to export_file."""
        raise NotImplementedError

    @abstractmethod
    def import_db_state(self, import_file: Path) -> None:
        """Import the new state of the DB from import_file."""
        raise NotImplementedError


class APIH2DatabaseContainer(APIWithDatabaseContainer):
    """API Container class using H2 as database."""

    def __init__(self, db_container: Container, jar_path: Path | None = None):
        """Determine path to H2 jar."""
        super().__init__(db_container=db_container)
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

    def _get_export_command(self, export_file: Path) -> str:
        str_command = f"SCRIPT TO '{export_file}';"
        return str_command

    def _get_import_command(self, import_file: Path) -> str:
        str_command = f"RUNSCRIPT FROM '{import_file}';"
        return str_command

    def export_db_state(self, export_file: Path) -> None:
        """Export the current state of the DB to export_file."""
        assert self.db_container
        cmnd = self._get_export_command(export_file)
        cmnd_file = "/tmp/export.sql"
        self.db_container.exec_run(f'sh -c "echo \\"{cmnd}\\" > {cmnd_file}"')
        exit_code, output = self.db_container.exec_run(f"""
        java -cp {str(self.jar_path)} org.h2.tools.RunScript \
        -url jdbc:h2:/opt/h2/testdb \
        -user sa \
        -script {cmnd_file}
        """)
        assert exit_code == 0, output

    def import_db_state(self, import_file: Path) -> None:
        """Import the new state of the DB from import_file."""
        assert self.db_container
        cmnd = self._get_import_command(import_file)
        cmnd_file = "/tmp_import.sql"
        self.db_container.exec_run(f'sh -c "echo \\"{cmnd}\\" > {cmnd_file}"')
        exit_code, output = self.db_container.exec_run(f"""
        java -cp {(self.jar_path)} org.h2.tools.RunScript \
        -url jdbc:h2:/opt/h2/testdb \
        -user sa \
        -script {cmnd_file}
        """)
        assert exit_code == 0, output


class APIMongoDBDatabaseContainer(APIWithDatabaseContainer):
    """API Container class using MongoDB as database."""

    def _get_export_command(self, export_file: Path) -> str:
        str_command = f"mongodump --db mydb --out {export_file}/"
        return str_command

    def _get_import_command(self, import_file: Path) -> str:
        str_command = f"mongorestore --db mydb {import_file}/mydb/"
        return str_command
