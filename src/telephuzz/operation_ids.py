"""File for generating operation ids."""

import hashlib
import re
from enum import Enum
from typing import cast


class Case(Enum):
    """Enum for common method name cases."""

    CAMEL = "camel"
    PASCAL = "pascal"
    SNAKE = "snake"

    @classmethod
    def _missing_(cls, value):
        """Fix case where input is not lowercase."""
        if isinstance(value, str):
            value = value.lower()
            for member in cls:
                if member.value == value:
                    return member
        return None


def generate_operation_id(method: str, path: str) -> str:
    """Generate an operation id based on the method and path."""
    # handle default path
    if path == "/":
        return f"{method.lower()}_default"

    # ignore query parameters
    path_segment = path[: path.find("?")] if "?" in path else path

    # ignore mitmproxy target prefix
    if ":" in path_segment[: path_segment.find("/", 1)]:
        path_segment = path_segment[path_segment.find("/", 1) :]

    path_part = (
        path_segment.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    )
    operation_id = f"{method.lower()}_{path_part.lower()}"
    # add hash of full path to avoid collisions
    hash_input = f"{method.upper()}:{path_segment}"
    operation_id += f"_h{hashlib.sha1(hash_input.encode()).hexdigest()[:8]}"

    return operation_id


def transform_case(string: str, case: Case) -> str:
    """Transform the string into the provided case format."""
    snake_regex = r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"
    camel_regex = r"^[a-z]+([A-Z][a-z0-9]*)*$"
    pascal_regex = r"^[A-Z][a-z0-9]*([A-Z][a-z0-9]*)*$"

    if re.fullmatch(snake_regex, string):
        current_case = Case.SNAKE
    elif re.fullmatch(camel_regex, string):
        current_case = Case.CAMEL
    elif re.fullmatch(pascal_regex, string):
        current_case = Case.PASCAL
    else:
        raise ValueError(f"Case of {string} should be in snake, camel or pascal case.")

    if case == current_case:
        return string

    match case:
        case Case.SNAKE:
            parts = list(filter(None, re.split(r"(?=[A-Z])", string)))
            return "_".join([cast(str, s).lower() for s in parts])
        case Case.CAMEL:
            if current_case == Case.SNAKE:
                parts = string.split("_")
                if len(parts) > 1:
                    parts = [parts[0]] + [part.capitalize() for part in parts[1:]]
                camel_operation_id = "".join(parts)
                assert re.fullmatch(camel_regex, camel_operation_id), (
                    f"Error while transforming to camel: {camel_operation_id}"
                )
                return camel_operation_id
            else:
                return string[0].swapcase() + string[1:]

        case Case.PASCAL:
            if current_case == Case.SNAKE:
                parts = string.split("_")
                parts = [part.capitalize() for part in parts]
                pascal_operation_id = "".join(parts)
                assert re.fullmatch(pascal_regex, pascal_operation_id), (
                    f"Error while transforming to pascal: {pascal_operation_id}"
                )
                return pascal_operation_id
            else:
                return string[0].swapcase() + string[1:]

        case _:
            raise ValueError("Invalid case.")
