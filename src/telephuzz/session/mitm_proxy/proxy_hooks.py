"""File for custom request and response handling for MITMProxyContainer."""

import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from mitmproxy import http

RESPONSE_PATH = "/responses"


def request(flow: http.HTTPFlow):
    """Handle custom encoding to route requests to API targets."""
    path = flow.request.path  # e.g. /server:8000/api/foo

    parts = path.lstrip("/").split("/", 1)

    if len(parts) < 2:
        return  # nothing to rewrite

    target, rest = parts

    # Expect "container:port"
    if ":" not in target:
        return

    host, port = target.split(":", 1)

    try:
        port_number = int(port)
    except ValueError:
        return

    # Rewrite request
    flow.request.host = host
    flow.request.port = port_number
    flow.request.path = "/" + rest


def response(flow: http.HTTPFlow):
    """Convert the response to JSON."""
    assert flow.response is not None
    # TODO fix body
    entry = {
        "request": {
            "method": flow.request.method,
            "url": flow.request.pretty_url,
            "headers": dict(flow.request.headers),
            "body": flow.request.get_text(),
        },
        "response": {
            "status_code": flow.response.status_code,
            "headers": dict(flow.response.headers),
            "body": flow.response.get_text(),
        },
    }

    response_id = time.time_ns()
    os.makedirs(RESPONSE_PATH, exist_ok=True)

    # get result_dir
    url = urlparse(flow.request.pretty_url)
    api_name = url.netloc[: url.netloc.find(":")]
    response_path = Path(RESPONSE_PATH) / api_name
    os.makedirs(response_path, exist_ok=True)

    with open(response_path / f"response_{response_id}.json", "w") as f:
        json.dump(entry, f)
