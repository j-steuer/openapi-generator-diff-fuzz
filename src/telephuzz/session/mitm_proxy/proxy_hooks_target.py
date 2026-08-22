"""File for custom response handling for MITMProxyContainer in single target mode."""

import base64
import json
import os
import time

from mitmproxy import http

RESPONSE_PATH = "/responses"


def response(flow: http.HTTPFlow):
    """Convert the response to JSON."""
    assert flow.response is not None

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
        "body": (
            base64.b64encode(flow.request.raw_content).decode("ascii")
            if flow.request.raw_content is not None
            else None
        ),
    }

    response_id = time.time_ns()
    os.makedirs(RESPONSE_PATH, exist_ok=True)
    with open(RESPONSE_PATH + f"/response_{response_id}.json", "w") as f:
        json.dump(entry, f)
