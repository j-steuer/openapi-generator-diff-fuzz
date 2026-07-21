"""Store information relevant for client library request source code generation."""

import ast
import json
from typing import Any

from telephuzz.config import get_config
from telephuzz.http_message import Request
from telephuzz.openapi_helpers import (
    extract_path_parameters,
    extract_path_variable_types,
    get_args,
    get_content_type,
    resolve_path,
)
from telephuzz.operation_ids import generate_operation_id

JSON_CONTENT = "application/json"


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

        self.body = request.body
        self.json_body = None
        self.path = request.path

        self.content_type = request.headers.get("Content-Type", None)
        if self.content_type is None:
            # infer content type from spec
            self.content_type = get_content_type(
                get_config().spec_str, request.method, request.path
            )

        self.authorization = request.headers.get("Authorization", None)

        if self.content_type == JSON_CONTENT:
            # process body to usable JSON
            try:
                self.json_body = ast.literal_eval(request.body)
            except ValueError:
                self.json_body = json.loads(request.body)

    def __repr__(self) -> str:
        """Repr method."""
        return str(self.__dict__)

    def _cast_parameters(self, query_parameters: dict, request: Request) -> dict:
        """Cast query parameters to correct type."""
        _params = dict(query_parameters)
        args = get_args(get_config().spec_str, request.method, request.path)
        for parameter, value in _params.items():
            if args[parameter] == "array" and not isinstance(value, list):
                _params[parameter] = [value]

        return _params

    def _get_operation_id(self, request: Request) -> str:
        """Resolve the operation id."""
        path = self._resolve_path(request.path)
        return generate_operation_id(request.method.value, path)

    def _get_query_parameters(self, request: Request) -> dict[str, Any]:
        """Resolve query parameters (including path variables)."""
        # check for path variables
        path_only = self._path_only(request.path)
        path = self._resolve_path(request.path)

        query_parameters = request.query_parameters
        if "{" in path:
            _path_params = extract_path_parameters(path, path_only)

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
        path = self._path_only(path)
        return resolve_path(path, get_config().spec_str)

    def _path_only(self, path: str) -> str:
        """Return the path without query parameters."""
        if "?" in path:
            path = path[: path.find("?")]

        return path
