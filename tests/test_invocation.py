"""Test invocation data processing."""

from copy import deepcopy

from conftest import TEST_CONFIG_BASE_PATH
from requests.models import CaseInsensitiveDict

from telephuzz.config import Config
from telephuzz.http_message import HTTPMethod, Request
from telephuzz.invocation_data import InvocationData


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
        body="üý»©TÎ",
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
        body="",
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
        body="üý»©TÎ",
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
        body="",
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
        body="üý»©TÎ",
        method=HTTPMethod.POST,
        path="/pet/-1714/uploadImage",
        query_parameters={"petId": -1714},
    )

    invocation = InvocationData(request)
    assert invocation.arg_types == {
        "petId": "integer",
        "additionalMetadata": "string",
        "requestBody": "string",
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
            '{"id": 1, '
            '"name": "test", '
            '"photoUrls": ["https://example.com/photo.jpg"], '
            '"status": "available", '
            '"tags": [{"id": 2, "name": "tag"}], '
            '"isCustom": true}'
        ),
        method=HTTPMethod.POST,
        path="/pet",
        query_parameters={},
    )
    empty_request = deepcopy(body_request)
    empty_request.body = "{}"

    invocation = InvocationData(empty_request)
    assert invocation.json_body is not None
    assert invocation.json_body == {}

    invocation = InvocationData(body_request)
    assert invocation.json_body is not None
    assert invocation.json_body["id"] == 1


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
            '{"name": "(", "photoUrls": ["\\u00d3", "\\u00c7", '
            '"\\uda19\\uddbd\\u00de7\\ud815\\udd85M\\u00e6", '
            '"\\udb9f\\udf7b\\u00e0\\udb96\\udf82\\u009d\\u00b5"], "id": -24336}'
        ),
        method=HTTPMethod.PUT,
        path="/pet",
        query_parameters={},
    )

    invocation = InvocationData(request)
    assert invocation.json_body is not None
    f"{invocation.json_body}".encode()
