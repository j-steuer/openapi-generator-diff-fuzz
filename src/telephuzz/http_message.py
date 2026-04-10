from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class HTTPMethod(Enum):
    """Enum for HTTP methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"


@dataclass
class HTTPMessage:
    """Abstract class for shared fields of Request and Response."""

    headers: Mapping[str, list[str]]
    body: bytes | str | None
    content_type: str | None


@dataclass
class Request(HTTPMessage):
    """Class for HTTP request fields relevant for the evaluation."""

    method: HTTPMethod
    target: str
    parameters: dict[str, list[str]]


@dataclass
class Response(HTTPMessage):
    """Class for HTTP response fields relevant for the evaluation."""

    status: int
    text: str
