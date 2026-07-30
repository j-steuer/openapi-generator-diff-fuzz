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


def test_request_from_json():
    """Test crating a request object from JSON."""
    data = """{
        "method": "GET",
        "url": "http://localhost:8000/testpath?id=2",
        "headers": {"testheader": 1},
        "query_parameters": {"id": 2},
        "body": "Test body"
    }"""

    request = Request.from_json(data)

    assert request.method == HTTPMethod.GET
    assert request.path == "/testpath?id=2"
    assert len(request.headers) == 1
    assert request.headers.get("testheader") == 1
    assert len(request.query_parameters) == 1
    assert request.query_parameters.get("id") == 2
    assert request.body == "Test body"


def test_response_hash():
    """Test hashing a response object."""
    response = Response(
        headers=CaseInsensitiveDict({"response_header": "test"}),
        body=r"{'test': 123}",
        status=404,
    )
    hash(response)

    # test hashing with empty body
    response.body = {}
    hash(response)


def test_response_from_json():
    """Test creating a response object from JSON."""
    data = """{
            "status_code": 200,
            "headers": {"testheader": 1},
            "body": "Test body"
        }"""

    response = Response.from_json(data)
    assert response.status == 200
    assert len(response.headers) == 1
    assert response.headers["testheader"] == 1
    assert response.body == "Test body"
