"""File for the class that stores the result of a request."""

from dataclasses import dataclass
from pathlib import Path

from telephuzz.http_message import Request, Response
from telephuzz.session.client_library import LibraryId


@dataclass(slots=True)
class RequestResult:
    """Store request result data important for the evaluation."""

    library: LibraryId
    request: Request
    response: Response | None
    db_state_before: Path | None
    db_state_after: Path | None

    def __hash__(self):
        """Hash method."""
        return hash(
            (
                self.library,
                self.request,
                self.response,
                self.db_state_before,
                self.db_state_after,
            )
        )
