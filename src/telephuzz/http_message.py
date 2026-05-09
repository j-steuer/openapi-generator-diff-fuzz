"""File for objects relating to requests and responses."""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from requests.structures import CaseInsensitiveDict


class HTTPMethod(Enum):
    """Enum for HTTP methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"
    OPTIONS = "OPTIONS"
    HEAD = "HEAD"
    TRACE = "TRACE"

    @classmethod
    def _missing_(cls, value):
        """Fix case where input is not capitalized."""
        if isinstance(value, str):
            value = value.upper()
            for member in cls:
                if member.value == value:
                    return member
        return None


@dataclass
class HTTPMessage:
    """Abstract class for shared fields of Request and Response."""

    headers: CaseInsensitiveDict
    body: Any


@dataclass
class Request(HTTPMessage):
    """Class for HTTP request fields relevant for the evaluation."""

    method: HTTPMethod
    path: str
    query_parameters: dict[str, Any]

    @classmethod
    def from_json(cls, json_data: Path | str):
        """Create a request from JSON."""
        if isinstance(json_data, Path):
            assert (
                json_data.exists()
                and json_data.is_file()
                and json_data.suffix == ".json"
            ), "Path must lead to a JSON file."

            with open(json_data, "r") as f:
                try:
                    data = json.load(f)
                except json.decoder.JSONDecodeError as e:
                    f.seek(0)
                    raise ValueError(
                        f"File content could not be loaded as JSON "
                        f"{repr(e)}: {f.read()}"
                    ) from e

        else:
            data = json.loads(json_data)

        if "request" in data:
            data = data["request"]

        parsed = urlsplit(data["url"])

        path = parsed.path
        query = parsed.query

        full_path = path
        if query:
            full_path += f"?{query}"

        try:
            return Request(
                headers=CaseInsensitiveDict(data["headers"]),
                body=data["body"],
                method=HTTPMethod(data["method"]),
                path=full_path,
                query_parameters=(
                    data["query_parameters"] if "query_parameters" in data else dict()
                ),
            )
        except KeyError as e:
            raise ValueError(f"JSON format was not valid ({repr(e)}): {data}") from e


@dataclass
class Response(HTTPMessage):
    """Class for HTTP response fields relevant for the evaluation."""

    status: int
    text: str | None

    @classmethod
    def from_json(cls, json_data: Path | str):
        """Create a response from JSON."""
        if isinstance(json_data, Path):
            assert (
                json_data.exists()
                and json_data.is_file()
                and json_data.suffix == ".json"
            ), "Path must lead to a JSON file."

            with open(json_data, "r") as f:
                data = json.load(f)

        else:
            data = json.loads(json_data)

        return Response(
            headers=CaseInsensitiveDict(data["headers"]),
            body=data["body"],
            status=data["status"],
            text=data["text"],
        )
