from dataclasses import dataclass

from telephuzz.http_message import HTTPMethod


@dataclass(slots=True)
class NondeterministicComponent:
    r"""Describes which parts of matching responses should be abstracted.

    A response is matched by `method` and `path`:

    - `method=None` matches all HTTP methods
    - `path=None` matches all paths

    The response content to abstract is determined by exactly one component type:

    - `json_component` abstracts a named field in a JSON response
    - `regex_component` abstracts text matched by a regular expression (case-sensitive)
    - If both are `None`, the entire response body is abstracted

    At most one of `json_component` and `regex_component` may be provided.

    Examples:
    - `method="GET", path=None`
      Matches and abstracts all GET responses.

    - `method=None, path="/example"`
      Matches and abstracts all responses for `/example`.

    - `json_component="token"`
      Abstracts all `token` JSON fields in matching responses.

    - `regex_component=r"Bearer\\s+\\S+"`
      Abstracts all text matching the regex pattern in matching responses.

    """

    method: HTTPMethod | str | None = None
    path: str | None = None  # TODO startswith?
    json_component: str | None = None
    regex_component: str | None = None
    component_count: int = 0

    def __post_init__(self) -> None:
        """Run compatibility checks."""
        if isinstance(self.method, str):
            try:
                self.method = HTTPMethod(self.method)
            except ValueError as e:
                raise ValueError(f"Invalid HTTP method {self.method}") from e

        if all(
            v is None
            for v in (
                self.method,
                self.path,
                self.json_component,
                self.regex_component,
            )
        ):
            raise ValueError(
                "At least one of method, path, json_component, "
                "or regex_component must be provided"
            )

        self.component_count = sum(
            v is not None for v in (self.json_component, self.regex_component)
        )

        if self.component_count > 1:
            raise ValueError(
                "At most one of json_component or regex_component may be provided"
            )
