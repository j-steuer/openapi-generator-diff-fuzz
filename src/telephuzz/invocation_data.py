"""Store information relevant for client library request source code generation."""

import json
from typing import Any, cast

from telephuzz.config import get_config
from telephuzz.http_message import Request, path_only
from telephuzz.openapi_helpers import (
    extract_path_parameters,
    extract_path_variable_types,
    get_args,
    get_content_type,
    resolve_path,
)
from telephuzz.operation_ids import generate_operation_id


class InvocationData:
    """Process general request information for client request code generation."""

    def __init__(self, request: Request):
        self.method = request.method
        self.operation_id = self._get_operation_id(request)

        self.query_parameters_without_path_vars = self._cast_parameters(
            dict(request.query_parameters), request
        )
        self.query_parameters = self._cast_parameters(
            self._get_query_parameters(request), request
        )
        self.arg_types = get_args(get_config().spec_str, request.method, request.path)

        self.body = request.body

        self.json_body = None
        self.path = request.path

        self.content_type = request.headers.get("Content-Type", None)
        if self.content_type is None:
            # infer content type from spec
            self.content_type = get_content_type(
                get_config().spec_str, request.method, request.path
            )

        self.send_body = "requestBody" in self.arg_types and (
            "json" not in cast(str, self.content_type) or self.body not in (None, b"")
        )

        self.authorization = request.headers.get("Authorization", None)

        if (
            self.content_type is not None
            and "json" in self.content_type
            and self.send_body
        ):
            # process body to usable JSON
            assert request.body is not None, "JSON body not provided for JSON request"
            self.json_body = json.loads(request.body)

            bodies = (
                list(self.json_body)
                if isinstance(self.json_body, list)
                else [dict(self.json_body)]
            )

            for idx, body in enumerate(bodies):
                assert isinstance(body, dict)

                # strip of unusable components
                # request generators may generate requests not
                # serializable by all clients
                # for all stripped components, at least one source will be provided
                # showing that one of the supported clients can not serialize it

                stripped_json_body = dict(body)

                for key, value in body.items():
                    # strip nested arrays
                    # (https://github.com/microsoft/kiota/issues/5159)
                    # while not a full match, kiota has several issues regarding
                    # (de-)serialization of nested arrays. As they are rarely used
                    # in OpenAPI schemas, this tool will not support them for the sake
                    # of simplicity and other client tools that may not support it

                    if isinstance(value, list):
                        if any(isinstance(v, list) for v in body[key]):
                            stripped_json_body.pop(key, None)

                bodies[idx] = stripped_json_body

            self.json_body = bodies if isinstance(self.json_body, list) else bodies[0]

    def __repr__(self) -> str:
        """Repr method."""
        return str(self.__dict__)

    def _cast_parameters(self, query_parameters: dict, request: Request) -> dict:
        """Cast query parameters to correct type."""
        _params = dict(query_parameters)
        args = get_args(get_config().spec_str, request.method, request.path)
        for parameter, value in _params.items():
            if args[parameter].schema_type == "array" and not isinstance(value, list):
                _params[parameter] = [value]
            if args[parameter].schema_type == "integer" and isinstance(value, str):
                _params[parameter] = int(value)

        return _params

    def _get_operation_id(self, request: Request) -> str:
        """Resolve the operation id."""
        path = self._resolve_path(request.path)
        return generate_operation_id(request.method.value, path)

    def _get_query_parameters(self, request: Request) -> dict[str, Any]:
        """Resolve query parameters (including path variables)."""
        # check for path variables
        base_path = path_only(request.path)
        path = self._resolve_path(request.path)

        query_parameters = dict(request.query_parameters)
        if "{" in path:
            _path_params = extract_path_parameters(path, base_path)

            # remove path variables from pure query parameters if present
            for path_param in _path_params.keys():
                if path_param in self.query_parameters_without_path_vars:
                    del self.query_parameters_without_path_vars[path_param]

            # cast integers
            path_parameter_types = extract_path_variable_types(
                get_config().spec_str, path
            )
            for parameter, value in path_parameter_types.items():
                if value == "integer":
                    _path_params[parameter] = int(_path_params[parameter])
                else:
                    _path_params[parameter] = str(_path_params[parameter])

            query_parameters.update(_path_params)

        return query_parameters

    def _resolve_path(self, path: str) -> str:
        """Resolve the concrete path."""
        path = path_only(path)
        return resolve_path(path, get_config().spec_str)
        """Return the path without query parameters."""
        if "?" in path:
            path = path[: path.find("?")]

        return path
