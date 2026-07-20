"""Test invocation data processing."""

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
