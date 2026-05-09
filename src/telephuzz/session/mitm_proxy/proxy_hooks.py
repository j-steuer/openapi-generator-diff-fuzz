"""File for custom request handling in MiTMProxy."""

import json
import sys

from mitmproxy import http


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

    # Optional: fix Host header
    flow.request.headers["Host"] = f"{host}:{port}"


def response(flow: http.HTTPFlow):
    """Convert the response to JSON."""
    assert flow.response is not None
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

    print(json.dumps(entry), file=sys.stdout)
