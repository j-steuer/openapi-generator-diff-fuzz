"""File for the abstractor class used to handle non-determinism in responses."""

from telephuzz.request_result import RequestResult


class Abstractor:
    """Replace non-determinstic components of responses with constant values."""

    def abstract(self, responses: set[RequestResult]) -> set[RequestResult]:
        """Transform all non-deterministic components of responses with constants."""
        raise NotImplementedError
