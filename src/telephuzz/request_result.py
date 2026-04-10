from dataclasses import dataclass
from pathlib import Path

from telephuzz.http_message import Request, Response
from telephuzz.session.client_library import LibraryId


@dataclass
class RequestResult:
    library: LibraryId
    request: Request
    response: Response
    db_state_before: Path
    db_state_after: Path
