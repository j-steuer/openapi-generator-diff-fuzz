"""File for code relating to client library containers."""

import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import textwrap
from _hashlib import HASH
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, cast

import docker
from docker.errors import ImageNotFound
from docker.models.containers import Container
from docker.models.images import Image

from telephuzz.config import get_config
from telephuzz.constants import CLIENT_PATH, GENERATORS_PATH, SPEC_PATH
from telephuzz.http_message import Response
from telephuzz.invocation_data import InvocationData
from telephuzz.openapi_helpers import get_version, resolve_path
from telephuzz.operation_ids import Case, transform_case

LibraryId = str

LIB_PATH = "/app"

logger = logging.getLogger(__name__)


class OpenAPIVersion(Enum):
    V_2 = "2.0.x"
    V_3_0 = "3.0.x"
    V_3_1 = "3.1.x"

    @classmethod
    def _missing_(cls, value):
        """Fix case where input is not capitalized."""
        if isinstance(value, str):
            for member in cls:
                if member.value.startswith(".".join(value.split(".")[:2])):
                    return member
        return None


@dataclass(slots=True)
class ModelCode:
    """Data class for code concerning JSON models."""

    import_code: str | None
    creation_code: str


def decode_output(output: bytes | Iterable[bytes]) -> str:
    """Decode output obtained through docker.exec_run."""
    return output.decode() if isinstance(output, bytes) else str(output)


# --- Base Class ---


class ClientLibraryContainer(ABC):
    """Abstract class for client library containers."""

    id: LibraryId
    container: Container | None
    method_case: Case = Case("snake")
    variable_case: Case = Case("snake")
    generator_script: str
    worker_script: str
    supported_versions: set[OpenAPIVersion]

    registry: dict = {}

    def __init__(self):
        """Initialize an existing image or create a new one if possible."""
        # build library
        if not SPEC_PATH.exists():
            with open(SPEC_PATH, "w") as spec:
                json.dump(get_config().spec, spec)

        self._check_version()

        generator_path = GENERATORS_PATH / self.generator_script
        library_path = CLIENT_PATH / self._get_library_dir_name()
        if not library_path.exists():
            try:
                subprocess.run([generator_path, library_path], check=True)
            except subprocess.CalledProcessError as e:
                raise RuntimeError("Error while generating client") from e

        image = self.get_image_by_hash(library_path)
        if image is None:
            raise ValueError("Hash should be obtainable" + " " + str(library_path))

        # set up container
        client = docker.from_env()

        container = client.containers.run(
            image=image,
            detach=True,
        )

        assert container is not None
        self.container = container

    def __init_subclass__(cls, **kwargs):
        """Obtain subclass id for registry lookup."""
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "id"):
            ClientLibraryContainer.registry[cls.id] = cls

    @classmethod
    def from_id(cls, id_):
        """Obtain concrete client library based on id."""
        return cls.registry[id_]

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

    def _check_version(self) -> None:
        """Verify that the tool supports the OpenAPI version."""
        _spec_version = get_version(get_config().spec)
        try:
            spec_version = OpenAPIVersion(_spec_version)
        except ValueError as e:
            raise ValueError(f"Unknown OpenAPI version: {_spec_version}") from e

        if spec_version not in self.supported_versions:
            raise ValueError(
                f"OpenAPI version {spec_version.value} is not supported by {self.id}"
            )

    def _get_library_dir_name(self) -> str:
        """Get name of directory where client library is stored."""
        spec_bytes = get_config().spec_str.encode()
        target_hash = hashlib.sha1(spec_bytes).hexdigest()[:8]
        return f"{self.id.replace(':', '-')}_{target_hash}"

    def _hash_file(self, path: Path, hash_func: HASH) -> None:
        with open(path, "rb") as f:
            while chunk := f.read(8192):
                hash_func.update(chunk)

    def _get_image_by_hash(self, library_path: Path, dockerfile: str) -> Image | None:

        if not library_path.exists():
            return None

        hash_func = hashlib.new("sha256")

        # Case 1: single file
        if library_path.is_file():
            self._hash_file(library_path, hash_func)

        # Case 2: directory → traverse all files
        else:
            all_files = [p for p in library_path.rglob("*") if p.is_file()]

            # sort for deterministic hashing
            for file_path in sorted(
                all_files, key=lambda p: str(p.relative_to(library_path))
            ):
                # include relative path to avoid collisions
                hash_func.update(str(file_path.relative_to(library_path)).encode())
                self._hash_file(file_path, hash_func)

        hash_string = hash_func.hexdigest()
        tag = f"telephuzz:{hash_string}"

        client = docker.from_env()
        try:
            # return Image if it already exists
            return client.images.get(tag)
        except ImageNotFound as e:
            # create new Image
            with tempfile.TemporaryDirectory() as tmpdir:
                # copy library into build context
                lib_dest = os.path.join(tmpdir, "lib")
                if library_path.is_dir():
                    shutil.copytree(library_path, lib_dest)
                else:
                    shutil.copy(library_path, lib_dest)

                # copy worker into build context
                worker_path = (
                    GENERATORS_PATH / "dockerfiles" / "workers" / self.worker_script
                )
                if not worker_path.exists():
                    raise ValueError(f"Worker path not found: {worker_path}") from e
                worker_dest = tmpdir
                if worker_path.is_dir():
                    shutil.copytree(worker_path, Path(worker_dest) / worker_path.name)
                else:
                    shutil.copy(worker_path, worker_dest)

                dockerfile_path = os.path.join(tmpdir, "Dockerfile")

                with open(dockerfile_path, "w") as f:  # type: ignore
                    f.write(dockerfile)  # type: ignore

                image, _ = client.images.build(path=tmpdir, tag=tag, rm=True)

            return image

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Define an optional method to store an image of the client library.

        The method should return the Image if it already exists or
        create a new one if possible.
        """
        return None

    @abstractmethod
    def _get_method_name(self, invocation: InvocationData) -> str:
        """Describe how to obtain the method name.

        To be used in _translate method.
        """
        raise NotImplementedError

    @abstractmethod
    def _translate(self, invocation: InvocationData, api_path: str) -> str | list[str]:
        """Translate the invocation.

        Translate the request into a command to call the target library.

        Args:
            request: The request to infer the method name from
            api_path: The url to call the api.

        """
        raise NotImplementedError

    def send(self, invocation: InvocationData, api_path: str) -> Response | str:
        """Send a request through the client library."""
        logger.debug(
            f"{self.id} sending request to API at {api_path}: {repr(invocation)}"
        )

        cased_invocation = self._apply_case_to_invocation(invocation)

        assert self.container is not None, "Container not set"
        exit_code, output = self.container.exec_run(
            cmd=self._translate(cased_invocation, api_path)
        )

        out = decode_output(output)
        if exit_code != 0:
            logger.debug(f"Client process exited with exit code {exit_code}: {out}")

        return out

    def _apply_case_to_invocation(self, invocation: InvocationData) -> InvocationData:
        """Apply method case to relevant invocation data."""

        def transform_dict(d: dict) -> dict:
            return {
                transform_case(k, self.variable_case) if k != "requestBody" else k: v
                for k, v in d.items()
            }

        cased_invocation = deepcopy(invocation)

        # operation id
        cased_invocation.operation_id = transform_case(
            invocation.operation_id, self.method_case
        )

        # query parameters
        cased_invocation.query_parameters = transform_dict(invocation.query_parameters)
        cased_invocation.query_parameters_without_path_vars = transform_dict(
            invocation.query_parameters_without_path_vars
        )
        cased_invocation.arg_types = transform_dict(invocation.arg_types)

        return cased_invocation

    # source code components

    @abstractmethod
    def _generate_code_models(self, invocation: InvocationData) -> ModelCode:
        """Generate code for handling custom models."""
        raise NotImplementedError


# --- Language-based Abstractions ---


class PythonCLC(ClientLibraryContainer):
    """Abstract class for python-based client library containers."""

    method_case = Case.SNAKE
    variable_case = Case.SNAKE
    base_image = "python:3.11-slim"
    worker_script = "worker.py"

    def __init__(self):
        """Initialize a Python-based client library."""
        super().__init__()
        assert self.container is not None

    @abstractmethod
    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        """Return the encoded code string that executes the invocation."""
        raise NotImplementedError

    def _translate(self, invocation: InvocationData, api_path: str) -> str | list[str]:
        assert self.container is not None, "Container not set"
        content = self._get_code(invocation, api_path)

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name="invocation.py")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        tar_stream.seek(0)

        self.container.put_archive("/tmp", tar_stream)

        return "touch /tmp/run.trigger"

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for Python-based libraries."""
        dockerfile = f"""
            FROM {self.base_image}
            WORKDIR {LIB_PATH}

            COPY lib {LIB_PATH}/lib
            RUN pip install -e {LIB_PATH}/lib

            COPY {self.worker_script} worker.py

            CMD ["python", "worker.py"]
        """
        return super()._get_image_by_hash(
            library_path=library_path,
            dockerfile=dockerfile,
        )


class GoCLC(ClientLibraryContainer):
    """Abstract class for Go-based client library containers."""

    method_case = Case.PASCAL
    variable_case = Case.CAMEL
    base_image = "golang:1.26"
    library_name: str

    def __init__(self):
        """Initialize a Go-based client library."""
        super().__init__()
        assert self.container is not None

    @abstractmethod
    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        """Return the encoded code string that executes the invocation."""
        raise NotImplementedError


class CsharpCLC(ClientLibraryContainer):
    """Abstract class for C#-based client library containers."""

    method_case = Case.PASCAL
    variable_case = Case.CAMEL
    base_image = "mcr.microsoft.com/dotnet/sdk:10.0"
    worker_script = "csharp-worker"

    def __init__(self):
        """Initialize a C#-based client library."""
        super().__init__()
        assert self.container is not None

    @abstractmethod
    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        """Return the encoded code string that executes the invocation."""
        raise NotImplementedError

    def _translate(self, invocation: InvocationData, api_path: str) -> str | list[str]:
        assert self.container is not None, "Container not set"
        content = self._get_code(invocation, api_path)

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name="invocation.csx")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        tar_stream.seek(0)

        self.container.put_archive("/app", tar_stream)

        input("continue")

        return "touch /tmp/run.trigger"

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for C#-based libraries."""
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}
                    COPY lib {LIB_PATH}/lib

                    RUN dotnet tool install -g dotnet-script
                    ENV PATH="$PATH:/root/.dotnet/tools"

                    RUN mkdir -p /tmp/dotnet-script-warmup

                    RUN echo 'Console.WriteLine("warmup");' > /tmp/warmup.csx
                    RUN dotnet script /tmp/warmup.csx

                    WORKDIR {LIB_PATH}/lib
                    RUN dotnet build -c Debug

                    RUN echo "=== OpenAPI DLL ===" \
                    && find /app -name "Org.OpenAPITools.dll" -print \
                    && test -f /app/lib/bin/Debug/net10.0/Org.OpenAPITools.dll

                    WORKDIR {LIB_PATH}
                    COPY csharp-worker {LIB_PATH}/csharp-worker

                    RUN dotnet publish csharp-worker/CsharpWorker.csproj \
                        -c Release \
                        -o /opt/csharp-worker \
                        --no-self-contained 
                        
                    RUN mkdir -p /worker 
                    
                    CMD ["dotnet", "/opt/csharp-worker/CsharpWorker.dll"] 
                    
                    WORKDIR {LIB_PATH}
                    """
        return super()._get_image_by_hash(library_path, dockerfile=dockerfile)


class TypeScriptCLC(ClientLibraryContainer):
    """Abstract class for TypeScript-based client library containers."""

    method_case = Case.CAMEL
    variable_case = Case.CAMEL
    base_image = "node:20-alpine"

    def __init__(self):
        """Initialize a TypeScript-based client library."""
        super().__init__()
        assert self.container is not None

    @abstractmethod
    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        """Return the encoded code string that executes the invocation."""
        raise NotImplementedError

    def _translate(self, invocation: InvocationData, api_path: str) -> str | list[str]:
        assert self.container is not None, "Container not set"
        content = self._get_code(invocation, api_path)

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name="invocation.ts")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        tar_stream.seek(0)

        self.container.put_archive(LIB_PATH, tar_stream)

        return f"npx tsx {LIB_PATH}/invocation.ts"

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for Go-based libraries."""
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}
                    COPY lib {LIB_PATH}/lib
                    RUN npm install axios
                    RUN npm i -D tsx
                    """
        return super()._get_image_by_hash(library_path, dockerfile=dockerfile)


# --- Mixins ---


class OperationIdBasedCLC(ClientLibraryContainer):
    """Mixin for containers where methods are named after operation ids."""

    def _get_method_name(self, invocation: InvocationData):
        library_method_name = transform_case(invocation.operation_id, self.method_case)

        return library_method_name


# --- Tool-based abstractions ---


class OpenAPIGen(OperationIdBasedCLC):
    supported_versions = {
        OpenAPIVersion.V_2,
        OpenAPIVersion.V_3_0,
        OpenAPIVersion.V_3_1,
    }


class SwaggerCodegen(OperationIdBasedCLC):
    supported_versions = {OpenAPIVersion.V_3_0}


class OpenAPIPythonClient(OperationIdBasedCLC):
    supported_versions = {OpenAPIVersion.V_3_0, OpenAPIVersion.V_3_1}


class Kiota:
    supported_versions = {OpenAPIVersion.V_3_0}


# --- Concrete Python Client Classes ---


def _get_model_name(invocation: InvocationData) -> str:
    """Obtain the name of a model.

    For instance, in the petshop API for OpenAPI Generator Python,
    refs usually result in objects: User, Pet, etc.
    This method resolves the names of these objects based on the
    queried endpoint and the OpenAPI spec.
    """
    model_name: str | None = ""
    if invocation.json_body is not None:
        model_name = min(cast(set, invocation.arg_types["requestBody"]))
    assert model_name is not None, (
        f"Obtaining args failed for {invocation.method} "
        f"{invocation.path} with body {invocation.body}"
    )
    return model_name


class OpenAPIGenPythonCLC(OpenAPIGen, PythonCLC):
    """Concrete client library for OpenAPI Generator Python."""

    id = "openapi-generator:python"
    generator_script = "openapi-generator-python.sh"

    def _generate_code_models(self, invocation: InvocationData) -> ModelCode:
        """Generate models for JSON bodies."""
        model_name = _get_model_name(invocation)
        model_name_module = transform_case(model_name, Case.SNAKE)
        model_name_class = transform_case(model_name, Case.PASCAL)
        import_code = (
            f"from openapi_client.models.{model_name_module} import {model_name_class}"
        )

        eval_body = invocation.json_body
        if isinstance(eval_body, list):
            # create list of objects
            model_list = [
                f"{model_name_class}.from_json({json.dumps(json.dumps(body))})"
                for body in eval_body
            ]
            creation_code = "[" + ", ".join(model_list) + "]"
        elif isinstance(eval_body, dict):
            body = json.dumps(eval_body)
            from_json = f"{model_name_class}.from_json({body!r}"
            creation_code = f"{model_name_module}={from_json})"
        else:
            raise NotImplementedError(
                f"Unhandled body type {type(eval_body)}: {invocation.body}"
            )

        return ModelCode(import_code=import_code, creation_code=creation_code)

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        model_name_str = ""
        query_parameters = invocation.query_parameters

        kwargs = ""
        if query_parameters:
            kwargs = ", ".join(f"{k}={repr(v)}" for k, v in query_parameters.items())

        if invocation.send_body:
            if invocation.json_body is not None:
                if invocation.arg_types["requestBody"] != {"object"}:
                    model_code = self._generate_code_models(invocation)
                    model_name_str += cast(str, model_code.import_code)
                    body_kwargs = model_code.creation_code
                else:
                    body_kwargs = f"body={repr(invocation.json_body)}"

            else:
                raw_body: str = invocation.body
                body_kwargs = f"body={raw_body.encode()!r}"

            kwargs += f"{', ' if query_parameters else ''}{body_kwargs}"

        if invocation.authorization is not None:
            auth = f', access_token="{invocation.authorization}"'
        else:
            auth = ""

        # TODO move replace to transforming invocation
        api = (
            get_config()
            .tag_lookup(invocation.method.value, invocation.path)
            .replace("-", "_")
        )
        api_class = transform_case(api, Case.PASCAL)

        content = textwrap.dedent(f"""
        from pprint import pprint

        from openapi_client import Configuration, ApiClient
        from openapi_client.api.{api}_api import {api_class}Api
        {model_name_str}

        config = Configuration(host="{api_path}"{auth})

        client = ApiClient(configuration=config)

        api = {api_class}Api(api_client=client)

        pprint(api.{self._get_method_name(invocation)}({kwargs}))
        """).encode()

        return content


class SwaggerCodegenPythonCLC(SwaggerCodegen, PythonCLC):
    """Client library class for Swagger Codegen Python."""

    id = "swagger-codegen:python"
    generator_script = "swagger-codegen-python.sh"

    def _generate_code_models(self, invocation: InvocationData) -> ModelCode:
        return ModelCode(None, f"body={invocation.json_body}")

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        query_parameters = invocation.query_parameters

        kwargs = ""
        if query_parameters:
            kwargs = ", ".join(f"{k}={repr(v)}" for k, v in query_parameters.items())

        if invocation.send_body:
            if invocation.json_body is not None:
                body_kwargs = self._generate_code_models(invocation).creation_code
            else:
                raw_body: str = invocation.body
                body_kwargs = f"body={repr(raw_body)}"

            kwargs += f"{', ' if query_parameters else ''}{body_kwargs}"

        api = (
            get_config()
            .tag_lookup(invocation.method.value, invocation.path)
            .replace("-", "_")
        )
        api_class = transform_case(api, Case.PASCAL)
        content = textwrap.dedent(f"""
        from pprint import pprint

        import swagger_client
        from swagger_client.configuration import Configuration
        from swagger_client.rest import ApiException

        config = Configuration()
        config.host = "{api_path}"
        api_instance = swagger_client.{api_class}Api(swagger_client.ApiClient(config))

        api_response = api_instance.{self._get_method_name(invocation)}({kwargs})
        pprint(api_response)
        """).encode()

        return content


class OpenAPIPythonClientCLC(OpenAPIPythonClient, PythonCLC):
    """Client library class for openapi-python-client."""

    id = "openapi-python-client:python"
    generator_script = "openapi-python-client.sh"

    def _get_method_name(self, invocation: InvocationData):
        # the hash is seperated
        method_name = super()._get_method_name(invocation)
        return method_name[:-8] + method_name[-8:]

    def _generate_code_models(self, invocation: InvocationData) -> ModelCode:

        if invocation.arg_types["requestBody"] != {"object"}:
            model_name = _get_model_name(invocation)
        else:
            model_name = f"{invocation.operation_id}_json_body"
        model_name_module = transform_case(model_name, Case.SNAKE)
        model_name_class = transform_case(model_name, Case.PASCAL)
        import_code = (
            f"from {self.module_name}.models.{model_name_module} "
            f"import {model_name_class}"
        )

        json_body = invocation.json_body
        if isinstance(json_body, list):
            model_list = [f"{model_name_class}.from_dict({body})" for body in json_body]
            creation_code = "body=[" + ", ".join(model_list) + "]"
        elif isinstance(json_body, dict):
            from_json = f"{model_name_class}.from_dict({json_body})"
            creation_code = f"body={from_json}"
        else:
            raise NotImplementedError(
                f"Unhandled body type {type(json_body)}: {invocation.body}"
            )

        return ModelCode(import_code=import_code, creation_code=creation_code)

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        # obtain main module name (should be only directory)
        if not hasattr(self, "module_name"):
            dir_name = self._get_library_dir_name()
            first_dir = next(d for d in CLIENT_PATH.iterdir() if dir_name in d.name)
            second_dir = next(
                d
                for d in first_dir.iterdir()
                if d.is_dir() and not d.name.startswith(".")
            )
            self.module_name = second_dir.name

        method_name = self._get_method_name(invocation)

        # resolve enums
        enum_import = ""
        joinable_values = dict()

        # enums
        for parameter in [p for p, v in invocation.arg_types.items() if v == "enum"]:
            if not enum_import:
                enum_import = (
                    f"from {self.module_name}.models.{invocation.operation_id}"
                    "_status import *"
                )

            enum_class_name = (
                f"{transform_case(invocation.operation_id, Case.PASCAL)}Status"
            )
            value = invocation.query_parameters.get(parameter)
            if value is not None:
                joinable_values[parameter] = f"{enum_class_name}({repr(value)})"
            else:
                # have to specifically set Unset, chooses default from enum otherwise
                joinable_values[parameter] = "Unset()"

        # other parameters
        for parameter, value in invocation.query_parameters.items():
            if invocation.arg_types[parameter] != "enum":
                joinable_values[parameter] = repr(value)

        kwargs = ", ".join(f"{k}={v}" for k, v in joinable_values.items())

        model_name_str = ""
        if invocation.send_body:
            if invocation.json_body is not None:
                model_code = self._generate_code_models(invocation)
                model_name_str = cast(str, model_code.import_code)
                body_kwargs = model_code.creation_code

            elif invocation.content_type == "application/octet-stream":
                raw_body: str = invocation.body
                bytes_io = f"BytesIO({raw_body.encode()!r})"
                body_kwargs = f"body=File({bytes_io})"
            else:
                raw_body = invocation.body
                body_kwargs = f"body={raw_body.encode()!r}"

            kwargs += f"{', ' if invocation.query_parameters else ''}{body_kwargs}"

        api = (
            get_config()
            .tag_lookup(invocation.method.value, invocation.path)
            .replace("-", "_")
        )

        content = textwrap.dedent(f"""
        from io import BytesIO
        from pprint import pprint

        from {self.module_name} import Client
        from {self.module_name}.api.{api} import {method_name}
        from {self.module_name}.types import File, Unset
        {model_name_str}
        {enum_import}


        client = Client("{api_path}")

        with client as client:
            my_data = {method_name}.sync_detailed(client=client, {kwargs})
            pprint(my_data)

        """).encode()

        return content


class KiotaPythonCLC(Kiota, PythonCLC):
    """Client library class for Kiota Python."""

    id = "kiota:python"
    generator_script = "kiota-python.sh"

    def _generate_code_models(self, invocation: InvocationData) -> ModelCode:
        def _parse_model(json_body: Any) -> str:
            """Parse the model for a single json_body."""
            parse_json_body: dict | str = json_body
            if not isinstance(parse_json_body, str):
                parse_json_body = json.dumps(parse_json_body)
            parse_node = f"""JsonParseNodeFactory().get_root_parse_node(
                    "application/json",
                    {repr(parse_json_body)}.encode()
                    )"""
            from_json = f"{parse_node}.get_object_value({model_name_class})"

            return from_json

        model_name = _get_model_name(invocation)
        model_name_module = transform_case(model_name, Case.SNAKE)
        model_name_class = transform_case(model_name, Case.PASCAL)
        import_code = (
            f"from my_kiota_client.models.{model_name_module} import {model_name_class}"
        )

        json_body = invocation.json_body
        if isinstance(json_body, list):
            model_list = [_parse_model(body) for body in json_body]
            creation_code = "body=[" + ", ".join(model_list) + "]"
        elif isinstance(json_body, dict):
            creation_code = f"body={_parse_model(json_body)}"
        else:
            raise NotImplementedError(
                f"Unhandled body type {type(json_body)}: {invocation.body}"
            )

        return ModelCode(import_code=import_code, creation_code=creation_code)

    def _get_method_name(self, invocation: InvocationData):
        path_components = resolve_path(invocation.path, get_config().spec_str).split(
            "/"
        )
        path_components = list(filter(None, path_components))
        for idx, path_component in enumerate(path_components):
            if path_component.startswith("{"):
                component_name = transform_case(
                    path_component[1:][:-1], self.method_case
                )
                value = invocation.query_parameters[component_name]
                if isinstance(value, str):
                    value = f'"""{value}"""'
                path_components[idx] = (
                    f"by_{transform_case(component_name, self.method_case)}({value})"
                )
            else:
                path_components[idx] = transform_case(path_component, self.method_case)

        path_components.append(f"{invocation.method.value.lower()}")

        return ".".join(path_components)

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:

        model_name_str = ""
        path_components = resolve_path(invocation.path, get_config().spec_str).split(
            "/"
        )

        json_object = invocation.json_body and invocation.arg_types["requestBody"] == {
            "object"
        }

        import_json_object = ""
        model_name_str = ""
        body_kwargs = ""
        if invocation.send_body:
            if not json_object:
                if invocation.json_body is not None:
                    model_code = self._generate_code_models(invocation)
                    model_name_str = cast(str, model_code.import_code)
                    body_kwargs = model_code.creation_code
                else:
                    raw_body: str = invocation.body
                    body_kwargs = f"body={raw_body.encode()!r}"
            else:
                base_path = [pc for pc in path_components if pc][0]
                module_path_prefix = ".".join(
                    [pc if "{" not in pc else "item" for pc in path_components if pc]
                )
                module_name = (
                    f"{base_path}_{invocation.method.value.lower()}_request_body"
                )
                module_path = f"{module_path_prefix}.{module_name}"
                class_name = transform_case(module_name, Case.PASCAL)
                import_json_object = (
                    f"from my_kiota_client.{module_path} import {class_name}"
                )
                body_kwargs = f"body={class_name}({repr(invocation.json_body)})"

        query_parameters = invocation.query_parameters_without_path_vars
        if query_parameters:
            path_components = [
                transform_case(c, self.method_case) if "{" not in c else "item"
                for c in path_components
                if c
            ]
            builder_module_prefix = (
                path_components[-1]
                if path_components[-1] != "item"
                else f"with_{path_components[-2]}_item"
            )
            request_builder_module = (
                f"{'.'.join(path_components)}.{builder_module_prefix}_request_builder"
            )
            request_builder = (
                f"{transform_case(builder_module_prefix, Case.PASCAL)}RequestBuilder"
            )
            import_query = (
                f"from my_kiota_client.{request_builder_module} "
                f"import {request_builder}"
            )
            _qp = invocation.query_parameters_without_path_vars.items()
            _eq = [f"{transform_case(k, self.method_case)}={repr(v)}" for k, v in _qp]
            _mth = invocation.method.value.capitalize()
            query_params = f"""{request_builder}.{request_builder}{_mth}QueryParameters(
                {",".join(_eq)}
            )"""
            request_config = f"""request_configuration = RequestConfiguration(
                query_parameters={query_params}
            )"""
        else:
            import_query = ""
            request_config = ""

        aauth = "kiota_abstractions.authentication.anonymous_authentication_provider"
        method_name = self._get_method_name(invocation)

        kwargs = ",".join(list(filter(None, [body_kwargs, request_config])))

        node_factory_import = (
            "from kiota_serialization_json.json_parse_node_factory"
            " import JsonParseNodeFactory"
        )
        content = textwrap.dedent(f"""
        import asyncio

        from {aauth} import (
            AnonymousAuthenticationProvider,
        )

        from kiota_http.httpx_request_adapter import HttpxRequestAdapter
        from kiota_abstractions.base_request_configuration import RequestConfiguration
        {node_factory_import}
        
        from my_kiota_client.posts_client import PostsClient
        {model_name_str}
        {import_query}
        {import_json_object}

        async def main():
            auth_provider = AnonymousAuthenticationProvider()

            adapter = HttpxRequestAdapter(auth_provider)
            adapter.base_url = "{api_path}"

            client = PostsClient(adapter)

            response = await client.{method_name}({kwargs})

            print(response)


        asyncio.run(main())
                """).encode()

        return content


# --- Concrete Go Client Classes ---


class OpenAPIGenGoCLC(OpenAPIGen, GoCLC):
    """Client library class for OpenAPI Generator Go."""

    id = "openapi-generator:go"
    generator_script = "openapi-generator-go.sh"

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        arg_string = ".".join(
            f"{k.capitalize()}({json.dumps(v)})"
            for k, v in invocation.query_parameters.items()
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
                {self._get_method_name(invocation)}(context.Background()).
                {arg_string}
                Execute()

            if err != nil {{
                log.Fatalf("Error calling API: %v\\nHTTP response: %v", err, httpRes)
            }}

            fmt.Println(resp)
        }}
        """).encode()

        return content


class SwaggerCodegenGoCLC(SwaggerCodegen, GoCLC):  # TODO might be broken
    """Client library class for Swagger Codegen Go."""

    id = "swagger-codegen:go"
    generator_script = "swagger-codegen-go.sh"

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for Go-based libraries."""
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}
                    COPY lib {LIB_PATH}/lib

                    RUN go mod init telephuzz
                    RUN go mod tidy
                    """
        return super()._get_image_by_hash(library_path, dockerfile=dockerfile)

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        return b""


class OapiGeneratorCLC(GoCLC, OperationIdBasedCLC):
    """Client library class for oapi generator."""

    id = "oapi-generator:go"
    generator_script = "oapi-codegen.sh"

    def _translate(self, invocation: InvocationData, api_path: str) -> str | list[str]:
        assert self.container is not None, "Container not set"
        content = self._get_code(invocation, api_path)

        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode="w") as tar:
            info = tarfile.TarInfo(name="invocation.go")
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
        tar_stream.seek(0)

        self.container.put_archive(f"{LIB_PATH}/lib", tar_stream)

        return f"go run {LIB_PATH}/lib/invocation.go"

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for Go-based libraries."""
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}/lib
                    COPY lib {LIB_PATH}/lib/oapi-codegen-client.go
                    
                    RUN go mod init telephuzz/client
                    RUN mkdir -p clients/client
                    RUN mv oapi-codegen-client.go clients/client/client.go
                    RUN go mod tidy
                    """
        return super()._get_image_by_hash(library_path, dockerfile=dockerfile)

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        arg_string = ",".join(
            f"{json.dumps(v)}" for v in invocation.query_parameters.values()
        )
        arg_string += "."
        method_name = self._get_method_name(invocation)
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


class OpenAPIGenTypeScriptCLC(OpenAPIGen, TypeScriptCLC):
    """Concrete client library for OpenAPI Generator TypeScript (Axios)."""

    id = "openapi-generator:typescript"
    generator_script = "openapi-generator-typescript.sh"

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        kwargs = ", ".join(json.dumps(v) for v in invocation.query_parameters.values())

        content = textwrap.dedent(f"""
        import {{ Configuration, DefaultApi }} from "./lib";

        const api = new DefaultApi(
        new Configuration({{
            basePath: "{api_path}",
        }})
        );

        async function main() {{
        try {{
            const greetRes = await api.{self._get_method_name(invocation)}({kwargs});

            console.log(greetRes.data);
        }} catch (err) {{
            console.error(err);
        }}
        }}

        main();

        """).encode()

        return content


class SwaggerCodegenTypeScriptCLC(SwaggerCodegen, TypeScriptCLC):
    """Concrete client library for Swagger Codegen TypeScript (Axios)."""

    id = "swagger-codegen:typescript"
    generator_script = "swagger-codegen-typescript.sh"

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        kwargs = ", ".join(json.dumps(v) for v in invocation.query_parameters.values())
        method_name = self._get_method_name(invocation)

        content = f"""
        // invocation.ts

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


class NswagTypeScriptCLC(TypeScriptCLC, OperationIdBasedCLC):
    """Concrete client library for Nswag TypeScript (Axios)."""

    id = "nswag:typescript"
    generator_script = "nswag-typescript.sh"

    method_case = Case.SNAKE  # uses operation id as is, default is SNAKE

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for Go-based libraries."""
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}
                    COPY lib {LIB_PATH}/lib/nswag-typescript-client.ts
                    RUN npm install axios
                    RUN npm i -D tsx
                    """
        return super()._get_image_by_hash(library_path, dockerfile=dockerfile)

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        kwargs = ", ".join(json.dumps(v) for v in invocation.query_parameters.values())

        client_type = invocation.method.value.capitalize()
        method_name = self._get_method_name(invocation)
        method_name = method_name[method_name.find("_") + 1 :]  # cut method

        # TODO fix client type stuff
        content = f"""
        import {{ GetClient }} from "./lib/nswag-typescript-client";

        async function main() {{
        const client = new {client_type}Client("{api_path}");

        const result = await client.{method_name}({kwargs});

        console.log("Response:", result);
        }}

        main().catch(console.error);

        """.encode()

        return content


class SwaggerTsAPICLC(TypeScriptCLC, OperationIdBasedCLC):
    """Concrete client library for swagger-typescript-api (Axios)."""

    id = "swagger-typescript-api:typescript"
    generator_script = "swagger-typescript-api.sh"

    def _get_method_name(self, invocation: InvocationData):
        method_name = super()._get_method_name(invocation)

        name, hash = method_name[:-8], method_name[-8:]
        processed_hash: list[str] = [hash[0].upper()]
        for i in range(1, len(hash)):
            c = hash[i]

            if c.isalpha():
                if processed_hash[i - 1].isdigit():
                    processed_hash.append(c.upper())
                else:
                    processed_hash.append(c.lower())
            else:
                processed_hash.append(c)

        return name + "".join(processed_hash)

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for Go-based libraries."""
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}
                    COPY lib {LIB_PATH}/lib/swagger-typescript-api.ts
                    RUN npm install axios
                    RUN npm i -D tsx
                    """
        return super()._get_image_by_hash(library_path, dockerfile=dockerfile)

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        arg_string = ",".join(
            f"{k.lower()}: {json.dumps(v)}"
            for k, v in invocation.query_parameters.items()
        )
        arg_string += ","

        method_name = self._get_method_name(invocation)

        content = f"""
        import {{ Api }} from "./lib/swagger-typescript-api";

        async function main() {{
        // Create API client instance
        const api = new Api({{
            baseURL: "{api_path}",
        }});

        try {{
            // Call /greet endpoint
            const response = await api.greet.{method_name}({{
            {arg_string}
            }});

            console.log("Response:", response.data);
        }} catch (err) {{
            console.error("Request failed:", err);
        }}
        }}

        main();
        """.encode()

        return content


class OrvalCLC(TypeScriptCLC, OperationIdBasedCLC):
    """Concrete client library for orval (Axios)."""

    id = "orval:typescript"
    generator_script = "orval.sh"

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Image creation for Go-based libraries."""
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}
                    COPY lib {LIB_PATH}/lib/orval.ts
                    RUN npm install axios
                    RUN npm i -D tsx
                    """
        return super()._get_image_by_hash(library_path, dockerfile=dockerfile)

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        arg_string = ",".join(
            f"{k.lower()}: {json.dumps(v)}"
            for k, v in invocation.query_parameters.items()
        )
        arg_string += ","

        content = f"""
        import axios from "axios";
        import {{ getFastAPI }} from "./lib/orval";

        async function main() {{
        // Optional: configure base URL globally
        axios.defaults.baseURL = "{api_path}";

        const api = getFastAPI();

        try {{
            const response = await api.{self._get_method_name(invocation)}(
            {{
                {arg_string}
            }}
            );

            console.log("Response:", response.data);
        }} catch (err) {{
            console.error("Request failed:", err);
        }}
        }}

        main();
        """.encode()

        return content


# --- Concrete C# Client classes ---


class OpenAPIGenCsharpCLC(OpenAPIGen, CsharpCLC):
    """Concrete client library class for OpenAPI Generator C#."""

    id = "openapi-generator:csharp"
    generator_script = "openapi-generator-csharp.sh"

    def _generate_code_models(self, invocation: InvocationData) -> ModelCode:
        """Generate models for JSON bodies."""
        model_name = _get_model_name(invocation)
        model_name_class = transform_case(model_name, Case.PASCAL)
        import_code = None

        eval_body = invocation.json_body
        if isinstance(eval_body, list):
            # create list of objects
            model_list = [
                f"JsonSerializer.Deserialize<{model_name_class}>({json.dumps(json.dumps(body))})"
                for body in eval_body
            ]
            creation_code = "{" + ", ".join(model_list) + "}"
        elif isinstance(eval_body, dict):
            body = json.dumps(eval_body)
            from_json = f"JsonSerializer.Deserialize<{model_name_class}>({body!r}"
            creation_code = from_json
        else:
            raise NotImplementedError(
                f"Unhandled body type {type(eval_body)}: {invocation.body}"
            )

        return ModelCode(import_code=import_code, creation_code=creation_code)

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        query_parameters = invocation.query_parameters

        kwargs = ""
        if query_parameters:
            kwargs = ", ".join(f"{k}: {repr(v)}" for k, v in query_parameters.items())

        if invocation.send_body:
            if invocation.json_body is not None:
                if invocation.arg_types["requestBody"] != {"object"}:
                    model_code = self._generate_code_models(invocation)
                    body_kwargs = model_code.creation_code
                else:
                    body_kwargs = f"{repr(invocation.json_body)}"

            else:
                raw_body: str = invocation.body
                body_kwargs = f"body={raw_body!r}"

            kwargs += f"{', ' if query_parameters else ''}{body_kwargs}"

        api = (
            get_config()
            .tag_lookup(invocation.method.value, invocation.path)
            .replace("-", "_")
        )
        api_class = transform_case(api, Case.PASCAL)

        method_name = self._get_method_name(invocation)

        content = textwrap.dedent(f"""
        #r "./lib/bin/Debug/net10.0/Org.OpenAPITools.dll"

        using System;
        using System.Net.Http;
        using System.Text.Json;
        using System.Threading;
        using System.Threading.Tasks;
        using Microsoft.Extensions.Logging.Abstractions;
        using Org.OpenAPITools;
        using Org.OpenAPITools.Api;
        using Org.OpenAPITools.Client;
        using Org.OpenAPITools.Model;

        class NoOpApiKeyTokenProvider : TokenProvider<ApiKeyToken>
        {{
            protected override ValueTask<ApiKeyToken> GetAsync(
                string header = "",
                CancellationToken cancellation = default)
            {{
                // Empty API key. The mock API does not require authentication.
                return ValueTask.FromResult(
                    new ApiKeyToken(
                        "",
                        ClientUtils.ApiKeyHeader.Api_key,
                        "api_key",
                        null));
            }}
        }}

        class NoOpOAuthTokenProvider : TokenProvider<OAuthToken>
        {{
            protected override ValueTask<OAuthToken> GetAsync(
                string header = "",
                CancellationToken cancellation = default)
            {{
                // Empty OAuth token. The mock API does not require authentication.
                return ValueTask.FromResult(
                    new OAuthToken(
                        "",
                        null));
            }}
        }}

        var httpClient = new HttpClient
        {{
            BaseAddress = new Uri("{api_path}")
        }};

        var jsonOptions = new JsonSerializerOptions
        {{
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
            PropertyNameCaseInsensitive = true
        }};

        var jsonOptionsProvider = new JsonSerializerOptionsProvider(jsonOptions);

        var logger = NullLogger<{api_class}Api>.Instance;
        var loggerFactory = NullLoggerFactory.Instance;
        var events = new {api_class}ApiEvents();

        var api = new {api_class}Api(
            logger,
            loggerFactory,
            httpClient,
            jsonOptionsProvider,
            events,
            new NoOpApiKeyTokenProvider(),
            new NoOpOAuthTokenProvider()
        );

        try
        {{
            var response = await api.{method_name}Async({kwargs});

            var payload = response.Ok();

            Console.WriteLine("Payload:");
            Console.WriteLine(payload);
        }}
        catch (Exception ex)
        {{
            Console.WriteLine("Request failed:");
            Console.WriteLine(ex);
        }}
        """).encode()

        return content


class SwaggerCodegenCsharpCLC(SwaggerCodegen, CsharpCLC):
    """Concrete client library class for Swagger Codegen C#."""

    id = "swagger-codegen:csharp"
    generator_script = "swagger-codegen-csharp.sh"

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        kwargs = ", ".join(json.dumps(v) for v in invocation.query_parameters.values())
        content = textwrap.dedent(f"""
        #r "./lib/bin/Debug/net471/IO.Swagger.dll"
        #r "./lib/bin/Debug/net471/RestSharp.dll"

        using System;
        using IO.Swagger.Api;
        using IO.Swagger.Client;

        var baseUrl = "{api_path}";

        var api = new DefaultApi(baseUrl);

        try
        {{
            var response = api.{self._get_method_name(invocation)}({kwargs});

            Console.WriteLine("Response:");
            Console.WriteLine(response);
        }}
        catch (ApiException ex)
        {{
            Console.WriteLine("API Error:");
            Console.WriteLine(ex.Message);
        }}
        """).encode()

        return content


class NswagCSharpCLC(CsharpCLC, OperationIdBasedCLC):
    """Concrete client library class for Nswag C#."""

    id = "nswag:csharp"
    generator_script = "nswag-csharp.sh"

    def get_image_by_hash(self, library_path: Path) -> Image | None:
        """Modify method to create project from scratch with single file cs."""
        dockerfile = f"""
                    FROM {self.base_image}
                    WORKDIR {LIB_PATH}

                    RUN dotnet tool install -g dotnet-script
                    ENV PATH="$PATH:/root/.dotnet/tools"
                    RUN mkdir -p /tmp/dotnet-script-warmup
                    RUN echo 'Console.WriteLine("warmup");' > /tmp/warmup.csx
                    RUN dotnet script /tmp/warmup.csx

                    RUN dotnet new classlib -n ApiClient
                    COPY lib {LIB_PATH}/ApiClient/nswag-csharp-client.cs
                    WORKDIR {LIB_PATH}/ApiClient
                    RUN dotnet add package Newtonsoft.Json
                    RUN dotnet build

                    WORKDIR {LIB_PATH}
                    """
        return super()._get_image_by_hash(library_path, dockerfile=dockerfile)

    def _get_method_name(self, invocation: InvocationData):
        name = super()._get_method_name(invocation)
        parts = re.findall(r"[A-Z][a-z0-9]*", name)
        name = "_".join(part for part in parts[1:])
        return name[:-8] + name[-8].lower() + name[-7:]

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        kwargs = ", ".join(json.dumps(v) for v in invocation.query_parameters.values())
        content = textwrap.dedent(f"""
        #r "nuget: Newtonsoft.Json, 13.0.3"
        #r "ApiClient/bin/Debug/net10.0/ApiClient.dll"

        using System;
        using System.Net.Http;
        using MyCompany.ApiClient;

        var httpClient = new HttpClient();

        var client = new {invocation.method.value.capitalize()}Client(
            "{api_path}",
            httpClient);

        var response = await client.{self._get_method_name(invocation)}Async({kwargs});

        Console.WriteLine(response);        
        """).encode()

        return content


class KiotaCSharpCLC(Kiota, CsharpCLC):
    """Concrete client library class for Kiota C#."""

    id = "kiota:csharp"
    generator_script = "kiota-csharp.sh"

    def _get_method_name(self, invocation: InvocationData):
        client_method = ".".join(
            part.capitalize() for part in invocation.path.strip("/").split("/") if part
        )
        client_method += f".{invocation.method.value.capitalize()}Async"

        return client_method

    def _get_code(self, invocation: InvocationData, api_path: str) -> bytes:
        module_name = self._get_method_name(invocation)
        module_name = module_name[: module_name.rfind(".")]

        lines = []
        for key, value in invocation.query_parameters.items():
            lines.append(
                f"config.QueryParameters.{key.capitalize()} = {json.dumps(value)};"
            )
        kwargs = "\n".join(lines)

        content = textwrap.dedent(f"""
        #r "nuget: Microsoft.Kiota.Abstractions, 1.22.1"
        #r "nuget: Microsoft.Kiota.Http.HttpClientLibrary, 1.22.1"
        #r "nuget: Microsoft.Kiota.Serialization.Json, 1.22.1"
        #r "nuget: Microsoft.Kiota.Serialization.Text, 1.22.1"
        #r "nuget: Microsoft.Kiota.Serialization.Form, 1.22.1"
        #r "nuget: Microsoft.Kiota.Serialization.Multipart, 1.22.1"

        #r "lib/bin/Debug/net8.0/Client.dll"

        using System;
        using System.Net.Http;
        using Microsoft.Kiota.Abstractions.Authentication;
        using Microsoft.Kiota.Http.HttpClientLibrary;
        using Microsoft.Kiota.Abstractions.Serialization;
        using Client;
        using Client.{module_name};

        var authProvider = new AnonymousAuthenticationProvider();

        var adapter = new HttpClientRequestAdapter(authProvider)
        {{
            BaseUrl = "{api_path}"
        }};

        var client = new PostsClient(adapter);

        var response = await client.{self._get_method_name(invocation)}(config =>
        {{
            {kwargs}
        }});

        Console.WriteLine(response);

       if (response is UntypedObject obj)
        {{
            var dict = obj.GetValue();

            foreach (var kv in dict)
            {{
                if (kv.Value is UntypedString str)
                {{
                    Console.WriteLine(str.GetValue());
                }}
            }}
        }}
                                  
        """).encode()

        return content
