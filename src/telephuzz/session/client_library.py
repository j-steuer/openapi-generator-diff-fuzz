"""File for code relating to client library containers."""

import hashlib
import io
import os
import shutil
import tarfile
import tempfile
import textwrap
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterable

import docker
from docker.errors import ImageNotFound
from docker.models.containers import Container
from docker.models.images import Image

from telephuzz.http_message import Request, Response
from telephuzz.operation_ids import Case, generate_operation_id, transform_case

LibraryId = str

LIB_PATH = "/app"


def decode_output(output: bytes | Iterable[bytes]) -> str:
    """Decode output obtained through docker.exec_run."""
    return output.decode() if isinstance(output, bytes) else str(output)


class ClientLibraryContainer(ABC):
    """Abstract class for client library containers."""

    id: LibraryId
    container: Container | None
    method_case: Case = Case("snake")

    def __init__(self, library_path: Path):
        """Initialize an existing image or create a new one if possible."""
        image = self.get_image_by_hash(library_path)
        if image is None:
            self.container = None
            return

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

    def __enter__(self):
        """Make a client library a context manager."""
        return self

    def __exit__(self, exc_type, exc, tb):
        """Run close method when context ends."""
        self.close()

    def close(self) -> None:
        """Kill the container after context ends."""
        if self.container is not None:
            self.container.remove(force=True)

            self.container = None

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Define an optional method to store an image of the client library.

        The method should return the Image if it already exists or
        create a new one if possible.
        """
        return None

    @abstractmethod
    def _get_method_name(self, request: Request) -> str:
        """Describe how to obtain the method name.

        To be used in _translate method.
        """
        raise NotImplementedError

    @abstractmethod
    def _translate(self, request: Request, api_path: str) -> str | list[str]:
        """Translate the request.

        Translate the request either into a callable or subprocess command to
        call the target library. Args:
            request: The request to infer the method name from
        """
        raise NotImplementedError

    def send(self, request: Request, api_path: str) -> Response | str:
        """Send a request through the client library."""
        assert self.container is not None, "Container not set"
        exit_code, output = self.container.exec_run(
            cmd=self._translate(request, api_path)
        )

        out = decode_output(output)
        assert exit_code == 0, f"Error occured while sending request: {out}"

        return out  # TODO parse to Response object


class PythonCLC(ClientLibraryContainer):
    """Abstract class for python-based client library containers."""

    method_case = Case("snake")

    def __init__(self, library_path: Path):
        """Initialize a python-based client library."""
        super().__init__(library_path=library_path)
        if self.container:
            # container is already running
            return

        # start up container without image
        client = docker.from_env()

        container = client.containers.run(
            image="python:3.11-slim",
            command="sleep infinity",  # keep container alive
            detach=True,
            volumes={
                str(library_path): {
                    "bind": LIB_PATH,
                    "mode": "rw",
                }
            },
            extra_hosts={
                "host.docker.internal": "host-gateway"
            },  # TODO remove once fixture fixed
        )

        # install library using pip
        exit_code, output = container.exec_run(
            f"pip install {LIB_PATH}", stdout=True, stderr=True
        )

        assert exit_code == 0, (
            f"Error while installing library using pip: {decode_output(output)}"
        )

        self.container = container

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for python-based libraries."""
        # use requirements.txt if available, otherwise pyproject.toml
        dependency_files = ["requirements.txt", "pyproject.toml"]
        for file in dependency_files:
            path = Path(os.path.join(library_path, file))
            if path.exists() and path.is_file():
                hash_func = hashlib.new("sha256")

                with open(path, "rb") as f:
                    while chunk := f.read(8192):
                        hash_func.update(chunk)

                hash_string = hash_func.hexdigest()
                tag = f"telephuzz:{hash_string}"

                client = docker.from_env()
                try:
                    # return Image if it already exists
                    return client.images.get(tag)
                except ImageNotFound:
                    # create new Image
                    dockerfile = f"""
                    FROM python:3.11-slim
                    WORKDIR {LIB_PATH}
                    COPY lib {LIB_PATH}/lib
                    RUN pip install {LIB_PATH}/lib
                    """  # TODO copy library after container is running

                    with tempfile.TemporaryDirectory() as tmpdir:
                        # copy library into build context
                        lib_dest = os.path.join(tmpdir, "lib")
                        shutil.copytree(library_path, lib_dest)

                        dockerfile_path = os.path.join(tmpdir, "Dockerfile")

                        with open(dockerfile_path, "w") as f:
                            f.write(dockerfile)

                        image, _ = client.images.build(path=tmpdir, tag=tag, rm=True)

                    return image

        # no fitting file found
        return None


class OperationIdBasedCLC(ClientLibraryContainer):
    """Mixin for containers where methods are named after operation ids."""

    def _get_method_name(self, request: Request) -> str:
        method, path = request.method, request.path
        operation_id = generate_operation_id(method.value, path)
        library_method_name = transform_case(operation_id, self.method_case)

        return library_method_name


class OpenAPIGenPythonCLC(PythonCLC, OperationIdBasedCLC):
    """Concrete client library for OpenAPI Generator Python."""

    id = "openapi_generator_python"

    def _translate(self, request: Request, api_path: str) -> str | list[str]:
        assert self.container is not None, "Container not set"

        kwargs = ", ".join(
            f"{k}={repr(v)}" for k, v in request.query_parameters.items()
        )
        content = textwrap.dedent(f"""
        from openapi_client import Configuration, ApiClient
        from openapi_client.api.default_api import DefaultApi

        config = Configuration(host="{api_path}")

        client = ApiClient(configuration=config)

        api = DefaultApi(api_client=client)

        api.{self._get_method_name(request)}({kwargs})
        """).encode()

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name="request.py")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        tar_stream.seek(0)

        self.container.put_archive("/tmp", tar_stream)

        return "python3 /tmp/request.py"
