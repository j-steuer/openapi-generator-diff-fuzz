"""File for code relating to API containers."""

import hashlib
from pathlib import Path

import docker
from docker.errors import ImageNotFound


class APIContainer:
    """A container for a target API."""

    def __init__(self, script_path: Path):
        """Initialize the API container."""
        assert (
            script_path.exists()
            and script_path.is_file()
            and script_path.suffix == ".sh"
        ), "script_path should lead to .sh file."

        hash_func = hashlib.new("sha256")

        with open(script_path, "rb") as f:
            while chunk := f.read(8192):
                hash_func.update(chunk)

        hash_string = hash_func.hexdigest()
        tag = f"telephuzz:api-{hash_string}"

        client = docker.from_env()
        try:
            image = client.images.get(tag)
            container = client.containers.run(
                image=image,
                command="sleep infinity",  # keep container alive
                detach=True,
                extra_hosts={
                    "host.docker.internal": "host-gateway"
                },  # TODO remove once fixture fixed
            )
            assert container is not None
            self.container = container

        except ImageNotFound:
            pass

        # set up container
        client = docker.from_env()

        container = client.containers.run(
            image=image,
            command="sleep infinity",  # keep container alive
            detach=True,
            extra_hosts={
                "host.docker.internal": "host-gateway"
            },  # TODO remove once fixture fixed
        )

        assert container is not None
        self.container = container

    def get_db_state(self) -> Path:
        """Get the current state of the database and write it to a file."""
        raise NotImplementedError  # TODO
