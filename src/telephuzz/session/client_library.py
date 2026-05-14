"""File for code relating to client library containers."""

import hashlib
import io
import json
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


# --- Base Class ---


class ClientLibraryContainer(ABC):
    """Abstract class for client library containers."""

    id: LibraryId
    container: Container | None
    method_case: Case = Case("snake")

    def __init__(
        self,
        library_path: Path,
    ):
        """Initialize an existing image or create a new one if possible."""
        image = self.get_image_by_hash(library_path)
        if image is None:
            # start up container without image TODO remove?
            raise ValueError("Hash should be obtainable")

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

    def _get_image_by_hash(
        self, library_path: Path, dependency_files: list[str], dockerfile: str
    ) -> Image | None:
        for file in dependency_files:
            path = (
                Path(os.path.join(library_path, file))
                if library_path.is_dir()
                else library_path
            )
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
                    with tempfile.TemporaryDirectory() as tmpdir:
                        # copy library into build context
                        lib_dest = os.path.join(tmpdir, "lib")
                        if library_path.is_dir():
                            shutil.copytree(library_path, lib_dest)
                        else:
                            shutil.copy(library_path, lib_dest)

                        dockerfile_path = os.path.join(tmpdir, "Dockerfile")

                        with open(dockerfile_path, "w") as f:
                            f.write(dockerfile)

                        image, _ = client.images.build(path=tmpdir, tag=tag, rm=True)

                    return image

        # no fitting file found
        return None

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

        Translate the request into a command to call the target library.

        Args:
            request: The request to infer the method name from
            api_path: The url to call the api.

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


# --- Language-based Abstractions ---


class PythonCLC(ClientLibraryContainer):
    """Abstract class for python-based client library containers."""

    method_case = Case.SNAKE
    base_image = "python:3.11-slim"

    def __init__(self, library_path: Path):
        """Initialize a Python-based client library."""
        super().__init__(
            library_path=library_path,
        )
        assert self.container is not None

    @abstractmethod
    def _get_code(self, request: Request, api_path: str) -> bytes:
        """Return the encoded code string that executes the request."""
        raise NotImplementedError

    def _translate(self, request: Request, api_path: str) -> str | list[str]:
        assert self.container is not None, "Container not set"
        content = self._get_code(request, api_path)

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name="request.py")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        tar_stream.seek(0)

        self.container.put_archive("/tmp", tar_stream)

        return "python3 /tmp/request.py"

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for Python-based libraries."""
        dependency_files = ["pyproject.toml", "setup.py", "requirements.txt"]
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}
                    COPY lib {LIB_PATH}/lib
                    RUN pip install -e {LIB_PATH}/lib
                    """
        return super()._get_image_by_hash(
            library_path=library_path,
            dependency_files=dependency_files,
            dockerfile=dockerfile,
        )


class GoCLC(ClientLibraryContainer):
    """Abstract class for Go-based client library containers."""

    method_case = Case.PASCAL
    base_image = "golang:1.26"
    library_name: str

    def __init__(self, library_path: Path):
        """Initialize a Go-based client library."""
        super().__init__(
            library_path=library_path,
        )
        assert self.container is not None

    @abstractmethod
    def _get_code(self, request: Request, api_path: str) -> bytes:
        """Return the encoded code string that executes the request."""
        raise NotImplementedError

    def _translate(self, request: Request, api_path: str) -> str | list[str]:
        assert self.container is not None, "Container not set"
        content = self._get_code(request, api_path)

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name="request.go")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        tar_stream.seek(0)

        self.container.put_archive("/app", tar_stream)

        return "go run /app/request.go"

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for Go-based libraries."""
        dependency_files = ["go.mod"]
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}
                    COPY lib {LIB_PATH}/lib
                    RUN go work init {LIB_PATH}/lib
                    """
        return super()._get_image_by_hash(
            library_path, dependency_files=dependency_files, dockerfile=dockerfile
        )


class JavaCLC(ClientLibraryContainer):
    """Abstract class for Java-based client library containers."""

    method_case = Case.CAMEL
    base_image = "eclipse-temurin:21"

    def __init__(self, library_path: Path):
        """Initialize a Java-based client library."""
        super().__init__(
            library_path=library_path,
        )
        assert self.container is not None


class SwiftCLC(ClientLibraryContainer):
    """Abstract class for Swift-based client library containers."""

    method_case = Case.CAMEL
    base_image = "swift:6.3.1"

    def __init__(self, library_path: Path):
        """Initialize a Swift-based client library."""
        super().__init__(
            library_path=library_path,
        )
        assert self.container is not None


class CsharpCLC(ClientLibraryContainer):
    """Abstract class for C#-based client library containers."""

    method_case = Case.PASCAL
    base_image = "mcr.microsoft.com/dotnet/sdk:10.0"

    def __init__(self, library_path: Path):
        """Initialize a C#-based client library."""
        super().__init__(
            library_path=library_path,
        )
        assert self.container is not None

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for C#-based libraries."""
        dependency_files = [".csproj"]  # TODO adjust
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}
                    COPY lib {LIB_PATH}/lib
                    """
        return super()._get_image_by_hash(
            library_path, dependency_files=dependency_files, dockerfile=dockerfile
        )


class TypeScriptCLC(ClientLibraryContainer):
    """Abstract class for TypeScript-based client library containers."""

    method_case = Case.CAMEL
    base_image = "node:20-alpine"

    def __init__(self, library_path: Path):
        """Initialize a TypeScript-based client library."""
        super().__init__(library_path=library_path)
        assert self.container is not None

    @abstractmethod
    def _get_code(self, request: Request, api_path: str) -> bytes:
        """Return the encoded code string that executes the request."""
        raise NotImplementedError

    def _translate(self, request: Request, api_path: str) -> str | list[str]:
        assert self.container is not None, "Container not set"
        content = self._get_code(request, api_path)

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name="request.ts")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        tar_stream.seek(0)

        self.container.put_archive(LIB_PATH, tar_stream)

        return f"npx tsx {LIB_PATH}/request.ts"

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for Go-based libraries."""
        dependency_files = ["api.ts"]  # TODO better file / method for inference
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}
                    COPY lib {LIB_PATH}/lib
                    RUN npm install axios
                    RUN npm i -D tsx
                    """
        return super()._get_image_by_hash(
            library_path, dependency_files=dependency_files, dockerfile=dockerfile
        )


# --- Mixins ---


class OperationIdBasedCLC(ClientLibraryContainer):
    """Mixin for containers where methods are named after operation ids."""

    def _get_method_name(self, request: Request) -> str:
        method, path = request.method, request.path
        operation_id = generate_operation_id(method.value, path)
        library_method_name = transform_case(operation_id, self.method_case)

        return library_method_name


# --- Concrete Python Client Classes ---


class OpenAPIGenPythonCLC(PythonCLC, OperationIdBasedCLC):
    """Concrete client library for OpenAPI Generator Python."""

    id = "openapi-generator:python"

    def _get_code(self, request: Request, api_path: str) -> bytes:
        kwargs = ", ".join(
            f"{k}={repr(v)}" for k, v in request.query_parameters.items()
        )
        content = textwrap.dedent(f"""
        from pprint import pprint

        from openapi_client import Configuration, ApiClient
        from openapi_client.api.default_api import DefaultApi

        config = Configuration(host="{api_path}")

        client = ApiClient(configuration=config)

        api = DefaultApi(api_client=client)

        pprint(api.{self._get_method_name(request)}({kwargs}))
        """).encode()

        return content


class SwaggerCodegenPythonCLC(PythonCLC, OperationIdBasedCLC):
    """Client library class for Swagger Codegen Python."""

    id = "swagger-codegen:python"

    def _get_code(self, request: Request, api_path: str) -> bytes:
        kwargs = ", ".join(
            f"{k}={repr(v)}" for k, v in request.query_parameters.items()
        )

        content = textwrap.dedent(f"""
        from pprint import pprint

        import swagger_client
        from swagger_client.configuration import Configuration
        from swagger_client.rest import ApiException

        config = Configuration()
        config.host = "{api_path}"
        api_instance = swagger_client.DefaultApi(swagger_client.ApiClient(config))

        api_response = api_instance.{self._get_method_name(request)}({kwargs})
        pprint(api_response)
        """).encode()

        return content


class OpenapiPythonGeneratorCLC(PythonCLC, OperationIdBasedCLC):
    """Client library class for openapi-python-generator."""

    def _get_method_name(self, request: Request) -> str:
        # the hash is seperated
        method_name = super()._get_method_name(request)
        return method_name[:-8] + "_" + method_name[-8:]

    def _get_code(self, request: Request, api_path: str) -> bytes:
        method_name = self._get_method_name(request)
        kwargs = ", ".join(
            f"{k}={repr(v)}" for k, v in request.query_parameters.items()
        )

        content = textwrap.dedent(f"""
        from pprint import pprint

        from fast_api_client import Client
        from fast_api_client.api.default import {method_name}

        client = Client("{api_path}")

        with client as client:
            my_data = {method_name}.sync_detailed(client=client, {kwargs})
            pprint(my_data)

        """).encode()

        return content


# --- Concrete Go Client Classes ---


class OpenAPIGenGoCLC(GoCLC, OperationIdBasedCLC):
    """Client library class for OpenAPI Generator Go."""

    def _get_code(self, request: Request, api_path: str) -> bytes:
        arg_string = ".".join(
            f"{k.capitalize()}({json.dumps(v)})"
            for k, v in request.query_parameters.items()
        )
        arg_string += "."

        content = textwrap.dedent(f"""
        package main

        import (
            "context"
            "fmt"
            "log"

            openapiclient "github.com/GIT_USER_ID/GIT_REPO_ID"
        )

        func main() {{
            // Create API client configuration
            cfg := openapiclient.NewConfiguration()
            cfg.Servers = openapiclient.ServerConfigurations{{
                {{
                    URL: "{api_path}",
                }},
            }}

            client := openapiclient.NewAPIClient(cfg)

            // Call the generated API method
            resp, httpRes, err := client.DefaultAPI.
                {self._get_method_name(request)}(context.Background()).
                {arg_string}
                Execute()

            if err != nil {{
                log.Fatalf("Error calling API: %v\\nHTTP response: %v", err, httpRes)
            }}

            fmt.Println(resp)
        }}
        """).encode()

        return content


class SwaggerCodegenGoCLC(GoCLC, OperationIdBasedCLC):  # TODO might be broken
    """Client library class for Swagger Codegen Go."""

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for Go-based libraries."""
        dependency_files = ["client.go"]  # TODO
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}
                    COPY lib {LIB_PATH}/lib

                    RUN go mod init telephuzz
                    RUN go mod tidy
                    """
        return super()._get_image_by_hash(
            library_path, dependency_files=dependency_files, dockerfile=dockerfile
        )

    def _get_code(self, request: Request, api_path: str) -> bytes:
        return b""


class OapiGeneratorCLC(GoCLC, OperationIdBasedCLC):
    """Client library class for oapi generator."""

    def _translate(self, request: Request, api_path: str) -> str | list[str]:
        assert self.container is not None, "Container not set"
        content = self._get_code(request, api_path)

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name="request.go")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        tar_stream.seek(0)

        self.container.put_archive(f"{LIB_PATH}/lib", tar_stream)

        return f"go run {LIB_PATH}/lib/request.go"

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for Go-based libraries."""
        dependency_files = ["oapi-codegen-client.go"]
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}/lib
                    COPY lib {LIB_PATH}/lib/oapi-codegen-client.go
                    
                    RUN go mod init telephuzz/client
                    RUN mkdir -p clients/client
                    RUN mv oapi-codegen-client.go clients/client/client.go
                    RUN go mod tidy
                    """
        return super()._get_image_by_hash(
            library_path, dependency_files=dependency_files, dockerfile=dockerfile
        )

    def _get_code(self, request: Request, api_path: str) -> bytes:
        arg_string = ",".join(
            f"{json.dumps(v)}" for v in request.query_parameters.values()
        )
        arg_string += "."
        method_name = self._get_method_name(request)
        content = f"""
        package main

        import (
            "context"
            "fmt"
            "log"

            "telephuzz/client/clients/client"
        )

        func main() {{
            ctx := context.Background()

            // Create API client
            c, err := client.NewClientWithResponses("{api_path}")
            if err != nil {{
                log.Fatal(err)
            }}

            // Call GET /greet
            resp, err := c.{method_name}WithResponse(ctx, &client.{method_name}Params{{
                Name: "Alice",
                Age:  30,
            }})
            if err != nil {{
                log.Fatal(err)
            }}

            fmt.Println("Status:", resp.Status())
            fmt.Println("Body:", string(resp.Body))
        }}

        """.encode()

        return content


# --- Concrete TypeScript Client classes


class OpenAPIGenTypeScriptCLC(TypeScriptCLC, OperationIdBasedCLC):
    """Concrete client library for OpenAPI Generator TypeScript (Axios)."""

    def _get_code(self, request: Request, api_path: str) -> bytes:
        kwargs = ", ".join(json.dumps(v) for v in request.query_parameters.values())

        content = textwrap.dedent(f"""
        import {{ Configuration, DefaultApi }} from "./lib";

        const api = new DefaultApi(
        new Configuration({{
            basePath: "{api_path}",
        }})
        );

        async function main() {{
        try {{
            const greetRes = await api.{self._get_method_name(request)}({kwargs});

            console.log(greetRes.data);
        }} catch (err) {{
            console.error(err);
        }}
        }}

        main();

        """).encode()

        return content


class SwaggerCodegenTypeScriptCLC(TypeScriptCLC, OperationIdBasedCLC):
    """Concrete client library for Swagger Codegen TypeScript (Axios)."""

    def _get_code(self, request: Request, api_path: str) -> bytes:
        kwargs = ", ".join(json.dumps(v) for v in request.query_parameters.values())
        method_name = self._get_method_name(request)

        content = f"""
        // request.ts

        import {{ Configuration, DefaultApi }} from "./lib";

        const api = new DefaultApi(
        new Configuration({{
            basePath: "{api_path}",
        }})
        );

        async function run() {{
        try {{
            const response = await api.{method_name}({kwargs});
            console.log("Response:", response.data);
        }} catch (err) {{
            console.error("Request failed:", err);
        }}
        }}

        // Immediately execute
        run();
        """.encode()

        return content
