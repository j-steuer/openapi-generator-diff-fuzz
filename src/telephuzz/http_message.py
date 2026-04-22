"""File for objects relating to requests and responses."""

from dataclasses import dataclass
from enum import Enum
from typing import Any

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
    content_type: str | None


@dataclass
class Request(HTTPMessage):
    """Class for HTTP request fields relevant for the evaluation."""

    method: HTTPMethod
    path: str
    path_parameters: dict[str, Any]
    query_parameters: dict[str, Any]


@dataclass
class Response(HTTPMessage):
    """Class for HTTP response fields relevant for the evaluation."""

    status: int
    text: str
