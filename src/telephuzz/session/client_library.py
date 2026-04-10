from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable

from docker.models.containers import Container

from telephuzz.http_message import Request, Response

LibraryId = str
Translation = Callable | list[str]


class Case(Enum):
    CAMEL = "camel"
    PASCAL = "pascal"
    SNAKE = "snake"


class ClientLibraryContainer(ABC):
    id: LibraryId
    container: Container

    @abstractmethod
    def _translate(self, request: Request) -> Translation:
        raise NotImplementedError

    def _transform_case(self, string: str, case: Case) -> str:
        raise NotImplementedError  # TODO

    def send(self, request: Request) -> Response:
        raise NotImplementedError  # TODO
