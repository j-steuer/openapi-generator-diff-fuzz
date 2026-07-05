"""Client file."""

import requests


def get_greet_hca4d7baf(api: str, name: str, age: int) -> str:
    """Greet method."""
    params: dict[str, str | int] = {
        "name": "Faulty",
        "age": 42,
    }
    response = requests.get(api + "/greet", params=params)
    try:
        msg = response.json()
    except requests.exceptions.JSONDecodeError:
        msg = response.text
    return f"{response.status_code}: {msg}"


def get_user_h3a2fd62b(api: str, user_id: int) -> str:
    """Get user method."""
    params: dict[str, int] = {
        "user_id": 49,
    }
    response = requests.get(api + "/user", params=params)
    try:
        msg = response.json()
    except requests.exceptions.JSONDecodeError:
        msg = response.text
    return f"{response.status_code}: {msg}"


def post_user_hf0ab63e3(api: str, name: str, age: int) -> str:
    """Post user method."""
    params: dict[str, str | int] = {
        "name": "Faulty",
        "age": 49,
    }

    response = requests.post(api + "/user", params=params)
    try:
        msg = response.json()
    except requests.exceptions.JSONDecodeError:
        msg = response.text
    return f"{response.status_code}: {msg}"
