"""File for generating operation ids."""

import hashlib
import re
from enum import Enum


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


def _hash_suffix(data: str, length: int = 7) -> str:
    """Return a deterministic lowercase alphabetic hash suffix.

    Having the suffix only consists of lowercase letters makes
    naming schemes based on the operation id used by generators
    more consistent and predictable.
    """
    value = int.from_bytes(hashlib.sha1(data.encode()).digest()[:5])
    chars = []
    while value:
        value, rem = divmod(value, 26)
        chars.append(chr(ord("a") + rem))

    suffix = "".join(reversed(chars))
    return suffix.rjust(length, "a")[-length:]


def generate_operation_id(method: str, path: str) -> str:
    """Generate an operation id based on the method and path."""
    # Handle default path
    if path == "/":
        return f"{method.lower()}_default"

    # Ignore query parameters
    path_segment = path.split("?", 1)[0]

    # Ignore mitmproxy target prefix
    if ":" in path_segment[: path_segment.find("/", 1)]:
        path_segment = path_segment[path_segment.find("/", 1) :]

    path_part = (
        path_segment.strip("/")
        .replace("/", "_")
        .replace("{", "")
        .replace("}", "")
        .lower()
    )

    # Add a deterministic alphabetic suffix to avoid collisions
    hash_input = f"{method.upper()}:{path_segment}"
    suffix = _hash_suffix(hash_input)

    return f"{method.lower()}_{path_part}_{suffix}"


def transform_case(string: str, case: Case, divide_uppercase=False) -> str:
    """Transform the string into the provided case format.

    divide_uppercase decides whether a sequence of uppercase letters
    are treated as a single word or as individual words. For instance,
    testWORD becomes test_word with divide_uppercase=False
    (used by OpenAPI Generator) and test_w_o_r_d with divide_uppercase=True
    (used by Kiota).
    """

    snake_regex = r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$"
    camel_regex = r"^[a-z][a-z0-9]*([A-Z][a-z0-9]*)*$"
    pascal_regex = r"^[A-Z][a-z0-9]*([A-Z][a-z0-9]*)*$"

    # Special characters can represent word boundaries.
    snake_string = re.sub(r"[^a-zA-Z0-9]", "_", string)
    compact_string = re.sub(r"[^a-zA-Z0-9]", "", string)

    if re.fullmatch(snake_regex, snake_string):
        current_case = Case.SNAKE
        string = snake_string
    elif re.fullmatch(camel_regex, compact_string):
        current_case = Case.CAMEL
        string = compact_string
    elif re.fullmatch(pascal_regex, compact_string):
        current_case = Case.PASCAL
        string = compact_string
    else:
        raise ValueError(
            f"Case of {string!r} should be in snake, camel or pascal case."
        )

    if case == current_case:
        return string

    match case:
        case Case.SNAKE:
            if current_case == Case.SNAKE:
                return string

            if divide_uppercase:
                # Keep an uppercase letter together with following lowercase
                # characters, but split consecutive uppercase letters.
                parts = re.findall(
                    r"[A-Z][a-z0-9]+|[A-Z](?![a-z0-9])|[a-z0-9]+",
                    string,
                )
            else:
                # camel/pascal -> snake
                parts = re.findall(
                    r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])",
                    string,
                )

            return "_".join(part.lower() for part in parts)

        case Case.CAMEL:
            if current_case == Case.SNAKE:
                parts = string.split("_")
                return parts[0] + "".join(
                    part.capitalize() for part in parts[1:] if part
                )

            # pascal -> camel
            return string[0].lower() + string[1:]

        case Case.PASCAL:
            if current_case == Case.SNAKE:
                parts = string.split("_")
                return "".join(part.capitalize() for part in parts if part)

            # camel -> pascal
            return string[0].upper() + string[1:]

        case _:
            raise ValueError("Invalid case.")
