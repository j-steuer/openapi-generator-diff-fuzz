"""File for code relating to client library containers."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable

from docker.models.containers import Container

from telephuzz.http_message import Request, Response

LibraryId = str
Translation = Callable | list[str]


class Case(Enum):
    """Enum for common method name cases."""

    CAMEL = "camel"
    PASCAL = "pascal"
    SNAKE = "snake"


class ClientLibraryContainer(ABC):
    """Abstract class for client library containers."""

    id: LibraryId
    container: Container

    @abstractmethod
    def _translate(self, request: Request) -> Translation:
        """Translate the request.

        Translate the request either into a callable or subprocess command to
        call the target library.
        """
        raise NotImplementedError

    def _transform_case(self, string: str, case: Case) -> str:
        """Transform the method name into the specified case."""
        raise NotImplementedError  # TODO

    def send(self, request: Request) -> Response:
        """Send a request through the client library."""
        raise NotImplementedError  # TODO
