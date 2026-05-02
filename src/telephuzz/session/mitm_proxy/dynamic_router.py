"""File for custom request handling in MiTMProxy."""

from mitmproxy import http
from requests.structures import CaseInsensitiveDict

from telephuzz.http_message import Response


class ResponseParser:
    """Class for response parsing."""

    def __init__(self):
        """Initialize response parsing class."""
        self.unchecked_responses = []
        self.checked_responses = []

    def response(self, flow: http.HTTPFlow):
        """Parse the response."""
        resp = flow.response
        assert resp is not None

        response = Response(
            headers=CaseInsensitiveDict(resp.headers),
            body=resp.content,
            content_type=resp.headers.get("content-type", None),  # TODO remove field?
            status=resp.status_code,
            text=resp.text,
        )
        # Do something with it
        self.unchecked_responses.append(response)


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
