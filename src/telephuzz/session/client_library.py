"""File for code relating to client library containers."""

from abc import ABC, abstractmethod
from typing import Callable

from docker.models.containers import Container

from telephuzz.http_message import Request, Response
from telephuzz.operation_ids import Case

LibraryId = str
Translation = Callable | list[str]


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

    def send(self, request: Request) -> Response:
        """Send a request through the client library."""
        raise NotImplementedError  # TODO


class OperationIdBasedCLC(ClientLibraryContainer):
    """General-purpose client library container.

    Can be used if the client-generation tool reliably uses the operation id
    of a method/path pair to generate method names.
    """

    def __init__(self, id: LibraryId, container: Container, case: Case):
        """Initialize the client library container."""
        self.id = id
        self.container = container
        self.case = case

    def _translate(self, request: Request) -> Translation:
        # method, path = request.method, request.path
        # operation_id = generate_operation_id(str(method), path)
        # library_method_name = transform_case(operation_id, self.case)

        # TODO create Translation based on library method name

        raise NotImplementedError
