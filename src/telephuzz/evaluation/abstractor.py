"""File for the abstractor class used to handle non-determinism in responses."""

import json
import logging
import re
from _collections_abc import Mapping
from typing import Any

from telephuzz.config import get_config
from telephuzz.evaluation.nondeterministic_component import NondeterministicComponent
from telephuzz.request_result import RequestResult

ABSTRACTED = "TELEPHUZZ_ABSTRACTED"

logger = logging.getLogger(__name__)


class Abstractor:
    """Replace non-determinstic components of responses with constant values."""

    def __init__(
        self,
        custom_headers: list[str] | None = None,
        custom_ndt_components: list[NondeterministicComponent] | None = None,
        abstract_x_headers: bool = True,
    ):
        """Initialize the Abstractor class.

        Args:
            custom_headers: Non-deterministic, implementation-based headers.
            custom_response_components: Non-deterministic response components.
            abstract_x_headers: Abstract headers with x- prefix. Default is True.

        """
        self.custom_headers = custom_headers if custom_headers else []
        self.custom_ndt_components = (
            custom_ndt_components if custom_ndt_components else []
        )

        self.nondeterministic_headers_pattern = []
        if abstract_x_headers:
            self.nondeterministic_headers_pattern.append(r"^x-.*")

        # add nondeterministic components from config
        self.custom_ndt_components.extend(get_config().nondeterministic_components)

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

        # handle custom nondeterministic components
        for nondeterministic_component in self.custom_ndt_components:
            # check request
            if (
                nondeterministic_component.method
                and request.method != nondeterministic_component.method
            ):
                continue

            normalized_path = (
                request.path[: request.path.find("?")]
                if "?" in request.path
                else request.path
            )
            if (
                nondeterministic_component.path
                and normalized_path != nondeterministic_component.path
            ):
                continue

            # apply abstraction
            if nondeterministic_component.component_count == 0:
                response.body = ABSTRACTED
            else:
                if nondeterministic_component.json_component:
                    try:
                        response_data = json.loads(response.body)
                    except json.decoder.JSONDecodeError:
                        method_str = (
                            "all"
                            if nondeterministic_component.method is None
                            else nondeterministic_component.method
                        )
                        path_str = (
                            "all"
                            if nondeterministic_component.path is None
                            else nondeterministic_component.path
                        )
                        logger.warning(
                            f"json_component abstraction intended for "
                            f"{method_str} {path_str}, "
                            f"but request returned non-JSON body."
                        )
                        continue

                    response_data = self._transform_json(
                        response_data, nondeterministic_component.json_component
                    )

                    response.body = json.dumps(response_data)

                elif nondeterministic_component.regex_component:
                    response.body = re.sub(
                        nondeterministic_component.regex_component,
                        ABSTRACTED,
                        response.body,
                    )
