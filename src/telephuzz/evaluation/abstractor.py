"""File for the abstractor class used to handle non-determinism in responses."""

import json
import re
from _collections_abc import Mapping
from dataclasses import dataclass
from typing import Any

from telephuzz.http_message import HTTPMethod
from telephuzz.request_result import RequestResult

ABSTRACTED = "TELEPHUZZ_ABSTRACTED"


@dataclass
class ResponseComponent:
    r"""Describes which parts of matching responses should be abstracted.

    A response is matched by `method` and `path`:

    - `method=None` matches all HTTP methods
    - `path=None` matches all paths

    The response content to abstract is determined by exactly one component type:

    - `json_component` abstracts a named field in a JSON response
    - `regex_component` abstracts text matched by a regular expression (case-sensitive)
    - If both are `None`, the entire response body is abstracted

    At most one of `json_component` and `regex_component` may be provided.

    Examples:
    - `method="GET", path=None`
      Matches and abstracts all GET responses.

    - `method=None, path="/example"`
      Matches and abstracts all responses for `/example`.

    - `json_component="token"`
      Abstracts all `token` JSON fields in matching responses.

    - `regex_component=r"Bearer\\s+\\S+"`
      Abstracts all text matching the regex pattern in matching responses.

    """

    method: HTTPMethod | None = None
    path: str | None = None  # TODO startswith?
    json_component: str | None = None
    regex_component: str | None = None

    def __post_init__(self) -> None:
        """Run compatibility checks."""
        if all(
            v is None
            for v in (
                self.method,
                self.path,
                self.json_component,
                self.regex_component,
            )
        ):
            raise ValueError(
                "At least one of method, path, json_component, "
                "or regex_component must be provided"
            )

        self.component_count = sum(
            v is not None for v in (self.json_component, self.regex_component)
        )

        if self.component_count > 1:
            raise ValueError(
                "At most one of json_component or regex_component may be provided"
            )


class Abstractor:
    """Replace non-determinstic components of responses with constant values."""

    def __init__(
        self,
        custom_headers: list[str] | None = None,
        custom_response_components: list[ResponseComponent] | None = None,
        abstract_x_headers: bool = True,
    ):
        """Initialize the Abstractor class.

        Args:
            custom_headers: Non-deterministic, implementation-based headers.
            custom_response_components: Non-deterministic response components.
            abstract_x_headers: Abstract headers with x- prefix. Default is True.

        """
        self.custom_headers = custom_headers if custom_headers else []
        self.custom_response_components = (
            custom_response_components if custom_response_components else []
        )

        self.nondeterministic_headers_pattern = []
        if abstract_x_headers:
            self.nondeterministic_headers_pattern.append(r"^x-.*")

    def _transform_json(self, json_data: Any, target_key: str):
        if isinstance(json_data, Mapping):
            return {
                key: (
                    ABSTRACTED
                    if key == target_key
                    else self._transform_json(value, target_key)
                )
                for key, value in json_data.items()
            }

        if isinstance(json_data, list):
            return [self._transform_json(item, target_key) for item in json_data]

        return json_data

    def abstract(self, result: RequestResult) -> None:
        """Transform all non-deterministic components of responses with constants."""
        # handle non-deterministic headers
        nondeterministic_headers = ["Date", "Etag"] + self.custom_headers

        request, response = result.request, result.response

        for pattern in self.nondeterministic_headers_pattern:
            nondeterministic_headers += [
                h
                for h in response.headers.keys()
                if re.fullmatch(pattern, h, flags=re.IGNORECASE)
            ]

        for nondeterministic_header in nondeterministic_headers:
            if nondeterministic_header in response.headers:
                response.headers[nondeterministic_header] = ABSTRACTED

        # handle custom response components
        for response_component in self.custom_response_components:
            # check request
            if (
                response_component.method
                and request.method != response_component.method
            ):
                continue

            if response_component.path and request.path != response_component.path:
                continue

            # apply abstraction
            if response_component.component_count == 0:
                response.body = ABSTRACTED
            else:
                if response_component.json_component:
                    try:
                        response_data = json.loads(response.body)
                    except json.decoder.JSONDecodeError as e:
                        raise ValueError(
                            f"json_component abstraction intended for "
                            f"{response_component.method} {response_component.path}, "
                            f"but request returned non-JSON body."
                        ) from e

                    response_data = self._transform_json(
                        response_data, response_component.json_component
                    )

                    response.body = json.dumps(response_data)

                elif response_component.regex_component:
                    response.body = re.sub(
                        response_component.regex_component, ABSTRACTED, response.body
                    )
