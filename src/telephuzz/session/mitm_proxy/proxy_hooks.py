"""File for custom request and response handling for MITMProxyContainer."""

import json
import logging
import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

from mitmproxy import http

RESPONSE_PATH = "/responses"

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


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

    # log request
    log_str = f"""
    Sending request:
    --------------------------------------
    Client: {flow.client_conn.peername}
    Method: {flow.request.method}
    Path: {flow.request.path}
    Full URL: {flow.request.url}
    Headers: {flow.request.headers}
    Body length: {len(flow.request.raw_content) if flow.request.raw_content else 0}
    Raw body content: {flow.request.raw_content!r}
    """

    logger.info(log_str)


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
    url = urlparse(flow.request.url)
    api_name = url.netloc[: url.netloc.find(":")]
    response_path = Path(RESPONSE_PATH) / api_name
    os.makedirs(response_path, exist_ok=True)

    with open(response_path / f"response_{response_id}.json", "w") as f:
        json.dump(entry, f)

    # log response
    log_str = f"""
    --------------------------------------
    Got response:
    --------------------------------------
    Client: {flow.client_conn.peername}
    Status: {flow.response.status_code}
    Headers: {flow.response.headers}
    Body length: {len(flow.response.raw_content) if flow.response.raw_content else 0}
    Raw body content: {flow.response.raw_content!r}
    """

    logger.info(log_str)
