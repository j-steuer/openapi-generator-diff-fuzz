from abc import ABC, abstractmethod
from telephuzz.http_message import Response, Request


class RequestGenerator(ABC):
    """Abstract class for the request generator."""

    @abstractmethod
    def generate(
        self, previous_responses: list[Response] | None
    ) -> list[Request] | None:
        """Abstract method for generating a request chain."""
        raise NotImplementedError
