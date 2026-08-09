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

    if flow.request.path == "/__mitmproxy_health":
        flow.response = http.Response.make(200)
        return

    query = flow.request.query
    query_parameters = {}
    for parameter in query.keys():
        values = query.get_all(parameter)
        query_parameters[parameter] = values[0] if len(values) == 1 else values

    entry = {
        "method": flow.request.method,
        "url": flow.request.pretty_url,
        "query_parameters": query_parameters,
        "headers": dict(flow.request.headers),
        "body": flow.request.get_text(),
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

    flow.response = http.Response.make(
        200,
        b"OK",
        {"Content-Type": "text/plain"},
    )
