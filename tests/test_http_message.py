"""Unit tests for HTTP message classes."""

from requests.models import CaseInsensitiveDict

from telephuzz.http_message import HTTPMethod, Request, Response


def test_request_hash():
    """Test hashing a request object."""
    request = Request(
        headers=CaseInsensitiveDict({"test_header": 123}),
        body="This is a test body.",
        method=HTTPMethod.POST,
        path="/example/path",
        query_parameters={"test_parameter": 567},
    )
    hash(request)

    # test hashing with empty body
    request.body = {}
    hash(request)


def test_response_hash():
    """Test hashing a response object."""
    response = Response(
        headers=CaseInsensitiveDict({"response_header": "test"}),
        body=r"{'test': 123}",
        status=404,
        text="Not found.",
    )
    hash(response)

    # test hashing with empty body
    response.body = {}
    hash(response)
