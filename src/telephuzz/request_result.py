"""File for the class that stores the result of a request."""

from dataclasses import dataclass

from telephuzz.http_message import Request
from telephuzz.session.client_library import LibraryId


@dataclass(slots=True)
class RequestResult:
    """Store request result data important for the evaluation."""

    library: LibraryId
    request: Request

    def __hash__(self):
        """Hash method."""
        return hash(
            (
                self.library,
                self.request,
            )
        )
