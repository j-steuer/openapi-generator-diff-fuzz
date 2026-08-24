"""Test invocation data processing."""

import json
from copy import deepcopy

from conftest import TEST_CONFIG_BASE_PATH
from requests.models import CaseInsensitiveDict

from telephuzz.config import Config
from telephuzz.http_message import HTTPMethod, Request
from telephuzz.invocation_data import InvocationData
from telephuzz.openapi_helpers import ParameterType


def test_strip_path_variables():
    """Query parameters without path vars should not contain path vars"""

    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

    request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "PMGCFW",
                "Content-Type": "application/octet-stream",
                "Content-Length": "6",
            }
        ),
        body=b"a",
        method=HTTPMethod.POST,
        path="/pet/-1714/uploadImage",
        query_parameters={"petId": -1714},
    )

    invocation = InvocationData(request)
    assert not invocation.query_parameters_without_path_vars


def test_cast_strings_to_array():
    """String parameters should be cast to array if type is array."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "W02CUe",
            }
        ),
        body=b"",
        method=HTTPMethod.GET,
        path="/pet/findByTags?tags=%C2%80%F0%A8%95%B3%F1%88%AC%93%C3%B6",
        query_parameters={"tags": "\x80𨕳\U00048b13ö"},
    )

    invocation = InvocationData(request)
    assert "tags" in invocation.query_parameters
    assert invocation.query_parameters["tags"] == [request.query_parameters["tags"]]


def test_infer_content_type():
    """Invocation should infer content type even if not provided."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    request_with_ctype = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "PMGCFW",
                "Content-Length": "6",
            }
        ),
        body=b"a",
        method=HTTPMethod.POST,
        path="/pet/-1714/uploadImage",
        query_parameters={"petId": -1714},
    )

    invocation = InvocationData(request_with_ctype)
    assert invocation.content_type == "application/octet-stream"

    request_without_ctype = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "W02CUe",
            }
        ),
        body=b"",
        method=HTTPMethod.GET,
        path="/pet/findByTags?tags=%C2%80%F0%A8%95%B3%F1%88%AC%93%C3%B6",
        query_parameters={"tags": "\x80𨕳\U00048b13ö"},
    )

    invocation = InvocationData(request_without_ctype)
    assert invocation.content_type is None


def test_arg_types():
    """Test obtaining parameter and body types from invocation."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "PMGCFW",
                "Content-Type": "application/octet-stream",
                "Content-Length": "6",
            }
        ),
        body=b"a",
        method=HTTPMethod.POST,
        path="/pet/-1714/uploadImage",
        query_parameters={"petId": -1714},
    )

    invocation = InvocationData(request)
    assert invocation.arg_types == {
        "petId": ParameterType(
            schema_type="integer",
            item_type=None,
            required=True,
        ),
        "additionalMetadata": ParameterType(
            schema_type="string",
            item_type=None,
            required=False,
        ),
        "requestBody": ParameterType(
            schema_type="string",
            item_type=None,
            required=False,
        ),
    }


def test_parse_json_body():
    """Test parsing a JSON body."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    body_request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "JXLuUJ",
                "Content-Type": "application/json",
                "Content-Length": "931",
            }
        ),
        body=(
            b'{"id": 1, '
            b'"name": "test", '
            b'"photoUrls": ["https://example.com/photo.jpg"], '
            b'"status": "available", '
            b'"tags": [{"id": 2, "name": "tag"}], '
            b'"isCustom": true}'
        ),
        method=HTTPMethod.POST,
        path="/pet",
        query_parameters={},
    )
    empty_request = deepcopy(body_request)
    empty_request.body = b"{}"

    invocation = InvocationData(empty_request)
    assert invocation.json_body is not None
    assert invocation.json_body == {}

    invocation = InvocationData(body_request)
    assert invocation.json_body is not None
    assert isinstance(invocation.json_body, dict)
    assert invocation.json_body["id"] == 1


def test_strip_unknown_body_properties():
    """Test that unknown JSON body properties are removed based on schema."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_config.yaml"

    request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "TEST123",
                "Content-Type": "application/json",
                "Content-Length": "100",
            }
        ),
        body=b'{"name": "Alice", "age": 30, "extra": "remove", "none": null}',
        method=HTTPMethod.POST,
        path="/user",
        query_parameters={},
    )

    invocation = InvocationData(request)
    assert invocation.json_body == {"name": "Alice", "age": 30}


def test_parse_surrogate_encoding():
    """Test request that used to throw an encoding error due to surrogates."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

    request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "NkdOLM",
                "Content-Type": "application/json",
                "Content-Length": "150",
            }
        ),
        body=(
            b'{"name": "(", "photoUrls": ["\\u00d3", "\\u00c7", '
            b'"\\uda19\\uddbd\\u00de7\\ud815\\udd85M\\u00e6", '
            b'"\\udb9f\\udf7b\\u00e0\\udb96\\udf82\\u009d\\u00b5"], "id": -24336}'
        ),
        method=HTTPMethod.PUT,
        path="/pet",
        query_parameters={},
    )

    invocation = InvocationData(request)
    assert invocation.json_body is not None
    f"{invocation.json_body}".encode()


def test_parse_array():
    """Array JSON should be parsable."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

    request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "rD5pQN",
                "Content-Type": "application/json",
                "Content-Length": "2",
            }
        ),
        body=b"[]",
        method=HTTPMethod.POST,
        path="/user/createWithList",
        query_parameters={},
    )

    request.body = json.dumps(
        [
            {
                "id": 10,
                "username": "theUser",
                "firstName": "John",
                "lastName": "James",
                "email": "john@email.com",
                "password": "12345",
                "phone": "12345",
                "userStatus": 1,
            },
            {
                "id": 11,
                "username": "theUser",
                "firstName": "John",
                "lastName": "James",
                "email": "john@email.com",
                "password": "12345",
                "phone": "12345",
                "userStatus": 1,
            },
        ]
    ).encode()

    invocation = InvocationData(request)
    assert isinstance(invocation.json_body, list)
    assert len(invocation.json_body) == 2
    assert invocation.json_body[0]["id"] != invocation.json_body[1]["id"]
    assert invocation.json_body[0]["password"] == invocation.json_body[1]["password"]


def test_cast_query_parameter_integers():
    """Test casting integers"""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"

    request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "Bi9xCz",
            }
        ),
        body=b"",
        method=HTTPMethod.GET,
        path="/jobExecutions?jobName=&exitCode=%F1%B8%98%B7%F3%91%AE%8ENf&limitPerJob=-137438953472",
        query_parameters={
            "jobName": "",
            "exitCode": "\U00078637\U000d1b8eNf",
            "limitPerJob": "-137438953472",
        },
    )

    invocation = InvocationData(request)
    assert invocation.query_parameters["jobName"] == ""
    assert invocation.query_parameters["exitCode"] == "\U00078637\U000d1b8eNf"
    assert invocation.query_parameters["limitPerJob"] == -137438953472


def test_no_sending_json_body_when_empty() -> None:
    """JSON body should not be sent if it is empty."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"

    request = Request(
        headers=CaseInsensitiveDict(
            {
                "Content-Type": "application/json",
            }
        ),
        body=b"",
        method=HTTPMethod.POST,
        path="/jobExecutions",
        query_parameters={},
    )

    invocation = InvocationData(request)
    assert not invocation.send_body

    # should still send for empty JSON
    request.body = b"{}"
    invocation = InvocationData(request)
    assert invocation.send_body


def test_send_non_json_body_when_empty() -> None:
    """Other bodies should be sent when empty."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"

    request = Request(
        headers=CaseInsensitiveDict(
            {
                "Content-Type": "application/octet-stream",
            }
        ),
        body=b"",
        method=HTTPMethod.POST,
        path="/jobExecutions",
        query_parameters={},
    )

    invocation = InvocationData(request)
    assert invocation.send_body


def test_invocation_does_not_modify_path_parameters() -> None:
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

    request = Request(
        headers=CaseInsensitiveDict(),
        body=b"",
        method=HTTPMethod.GET,
        path="/pet/0",
        query_parameters={"petId": "0"},
    )

    before = deepcopy(request)

    InvocationData(request)

    assert request == before
    assert request.query_parameters == {"petId": "0"}
