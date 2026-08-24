"""Unit tests for HTTP message classes."""

import base64
from copy import deepcopy

from requests.models import CaseInsensitiveDict

from telephuzz.http_message import HTTPMethod, Request


def test_request_hash():
    """Test hashing a request object."""
    request = Request(
        headers=CaseInsensitiveDict({"test_header": 123}),
        body=b"This is a test body.",
        method=HTTPMethod.POST,
        path="/example/path",
        query_parameters={"test_parameter": 567},
    )
    hash(request)

    # test hashing with empty body
    request.body = None
    hash(request)


def test_request_from_json():
    """Test crating a request object from JSON."""
    data = f"""{{
        "method": "GET",
        "url": "http://localhost:8000/testpath?id=2",
        "headers": {{"testheader": 1, "Content-Type": "application/json"}},
        "query_parameters": {{"id": 2}},
        "body": "{base64.b64encode(b"Test body").decode("ascii")}"
    }}"""

    request = Request.from_json(data)

    assert request.method == HTTPMethod.GET
    assert request.path == "/testpath?id=2"
    assert len(request.headers) == 1
    assert request.headers.get("content-type") == "application/json"
    assert len(request.query_parameters) == 1
    assert request.query_parameters.get("id") == 2
    assert request.body == b"Test body"


def test_base_path_equivalence(basic_request):
    """Test that order of query parameters does not matter for __eq__."""
    request1 = deepcopy(basic_request)
    request1.path = "/greet?age=0&name="
    request2 = deepcopy(basic_request)
    request2.path = "/greet?name=&age=0"

    assert request1 == request2


def test_json_body_equivalence(basic_request):
    """Test that bodies loadable as json are evaluated as json."""
    request1 = deepcopy(basic_request)
    request1.body = '{"age": 4800, "name": ""}'
    request2 = deepcopy(basic_request)
    request2.body = '{"name": "", "age": 4800}'

    assert request1 == request2
