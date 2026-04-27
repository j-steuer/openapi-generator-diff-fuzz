"""File for generating operation ids."""

import hashlib
from enum import Enum


class Case(Enum):
    """Enum for common method name cases."""

    CAMEL = "camel"
    PASCAL = "pascal"
    SNAKE = "snake"


def generate_operation_id(method: str, path: str) -> str:
    """Generate an operation id based on the method and path."""
    path_part = path.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    operation_id = f"{method.lower()}_{path_part}"
    # add hash of full path to avoid collisions
    operation_id += f"_{hashlib.sha1(path.encode()).hexdigest()[:8]}"

    return operation_id


def transform_case(string: str, case: Case) -> str:
    """Transform the string into the provided case format."""
    raise NotImplementedError
