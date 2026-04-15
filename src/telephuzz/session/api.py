"""File for code relating to API containers."""

from pathlib import Path

from docker.models.containers import Container


class APIContainer:
    """A container for a target API."""

    def __init__(self, container: Container):
        """Initialize the API container."""
        self.container = container

    def get_db_state(self) -> Path:
        """Get the current state of the database and write it to a file."""
        raise NotImplementedError  # TODO
