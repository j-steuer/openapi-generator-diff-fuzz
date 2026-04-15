"""Helper methods relating to the Docker SDK for Python."""

import os
from pathlib import Path

import docker
from docker.errors import ImageNotFound
from docker.models.containers import Container
from docker.models.images import Image

from telephuzz.constants import DOCKER_NETWORK_NAME


def create_image(path: Path, tag: str) -> Image:
    """Create an image from a Dockerfile at path or return existing image."""
    if ":" not in tag:
        tag += ":latest"

    client = docker.client.from_env()

    try:
        # return if image already exists
        return client.images.get(tag)
    except ImageNotFound:
        pass

    # check that path is valid
    if not (path.is_dir() and "Dockerfile" in os.listdir(path)):
        raise ValueError(
            f"{path} needs to point to a directory containing a file named Dockerfile."
        )

    # build image
    image, logs = client.images.build(path=str(path), tag=tag)
    return image


def add_container_to_network(image: str, name: str) -> Container:
    """Create a container and add it to the telephuzz docker network."""
    client = docker.client.from_env()

    # check that image exists
    try:
        client.images.get(image)
    except ImageNotFound as e:
        raise ImageNotFound(
            f"Image {image} needs to be created before calling this method."
        ) from e

    container = client.containers.run(
        image=image, name=name, detach=True, network=DOCKER_NETWORK_NAME
    )

    return container
