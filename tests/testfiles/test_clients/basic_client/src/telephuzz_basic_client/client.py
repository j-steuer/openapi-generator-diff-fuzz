"""Client file."""

import requests


def get_greet_erwiiix(api: str, name: str, age: int) -> str:
    """Greet method."""
    params: dict[str, str | int] = {
        "name": name,
        "age": age,
    }
    response = requests.get(api + "/greet", params=params)
    try:
        msg = response.json()
    except requests.exceptions.JSONDecodeError:
        msg = response.text
    return f"{response.status_code}: {msg}"


def get_user_czvfdpt(api: str, user_id: int) -> str:
    """Get user method."""
    params: dict[str, int] = {
        "user_id": user_id,
    }
    response = requests.get(api + "/user", params=params)
    try:
        msg = response.json()
    except requests.exceptions.JSONDecodeError:
        msg = response.text
    return f"{response.status_code}: {msg}"


def post_user_sczmypr(api: str, name: str, age: int) -> str:
    """Post user method."""
    body: dict[str, str | int] = {
        "name": name,
        "age": age,
    }

    response = requests.post(api + "/user", json=body)
    try:
        msg = response.json()
    except requests.exceptions.JSONDecodeError:
        msg = response.text
    return f"{response.status_code}: {msg}"
