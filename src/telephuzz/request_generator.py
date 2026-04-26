"""File for code relating to request generation."""

from abc import ABC, abstractmethod
from pathlib import Path

from telephuzz.http_message import Request, Response


class RequestGenerator(ABC):
    """Abstract class for the request generator."""

    @abstractmethod
    def generate(
        self, previous_responses: list[Response] | None = None
    ) -> list[Request] | None:
        """Abstract method for generating a request chain."""
        raise NotImplementedError


class OASRequestGenerator(RequestGenerator):
    """Abstract class for a request generator that takes an OpenAPI spec as input."""

    oas: Path


class SchemathesisGenerator(OASRequestGenerator):
    """Request generator based on Schemathesis."""

    def __init__(self, oas: Path):
        """Initialize the SchemathesisGenerator."""
        self.oas = oas

    def generate(
        self, previous_responses: list[Response] | None = None
    ) -> list[Request] | None:
        """Generate requests based on Schemathesis."""
        pass  # TODO
