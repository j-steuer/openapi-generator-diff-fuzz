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
