from pathlib import Path

from docker.models.containers import Container


class APIContainer:
    def __init__(self, container: Container):
        self.container = container

    def get_db_state(self) -> Path:
        raise NotImplementedError  # TODO
