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

    @abstractmethod
    def get_state(self, out: Path) -> None:
        """Write the state to a file that can be used for hashing and diff."""
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

    def _run_command(self, cmnd: str) -> None:
        """Run the provided command."""
        assert self.db_container
        cmnd_file = "/tmp_import.sql"
        self.db_container.exec_run(f'sh -c "echo \\"{cmnd}\\" > {cmnd_file}"')
        exit_code, output = self.db_container.exec_run(f"""
        java -cp {(self.jar_path)} org.h2.tools.RunScript \
        -url jdbc:h2:/opt/h2/testdb \
        -user sa \
        -script {cmnd_file}
        """)
        assert exit_code == 0, output

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
        # TODO postprocesss, remove SALT and HASH
        assert self.db_container
        cmnd = f"SCRIPT SIMPLE TO '{str(out)}';"
        self._run_command(cmnd)


class APIMongoDBDatabaseContainer(APIWithDatabaseContainer):
    """API Container class using MongoDB as database."""

    def _run_command(self, cmnd: str) -> None:
        assert self.db_container is not None
        exit_code, output = self.db_container.exec_run(cmnd)
        assert exit_code == 0, output

    def export_db_state(self, export_file: Path) -> None:
        """Export the current state of the DB to export_file."""
        str_command = f"mongodump --out {export_file}"
        self._run_command(str_command)

    def import_db_state(self, import_file: Path) -> None:
        """Import the new state of the DB from import_file."""
        str_command = f"mongorestore --drop {import_file}"
        self._run_command(str_command)

    def get_state(self, out: Path) -> None:
        """Write the state to a file that can be used for hashing and diff."""
        pass  # TODO
