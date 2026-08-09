"""Tests for DiffFuzzer."""

import os
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from requests.models import CaseInsensitiveDict

from telephuzz.config import Config
from telephuzz.evaluation.evaluator import DiffEvaluator
from telephuzz.http_message import HTTPMethod, Request
from telephuzz.request_result import RequestResult


@pytest.fixture
def mock_invocation_data(monkeypatch):
    invocation_data = MagicMock()
    invocation_data.json_body = None

    monkeypatch.setattr(
        "telephuzz.evaluation.evaluator.InvocationData",
        lambda request: invocation_data,
    )

    return invocation_data


def test_same_request_responses(mock_invocation_data):
    """Test that DiffFuzzer returns an empty set if no diffs."""
    evaluator = DiffEvaluator()

    request = Request(
        headers=CaseInsensitiveDict({"test_header": 123}),
        body="This is a test body.",
        method=HTTPMethod.POST,
        path="/example/path",
        query_parameters={"test_parameter": 567},
    )
    # TODO adjust when db comp implemented
    result1 = RequestResult("Lib1", request)
    result2 = RequestResult("Lib2", request)
    result3 = RequestResult("Lib3", request)
    libs = evaluator.eval({result1, result2, result3}, request, log_errors=False)

    assert len(libs) == 0


def test_same_diff_request(mock_invocation_data):
    """Test that DiffFuzzer recognizes a diff in requests and returns the library."""
    evaluator = DiffEvaluator()

    request = Request(
        headers=CaseInsensitiveDict({"test_header": 123}),
        body="This is a test body.",
        method=HTTPMethod.POST,
        path="/example/path",
        query_parameters={"test_parameter": 567},
    )
    wrong_request = deepcopy(request)
    request.body = "Wrong body."
    # TODO adjust when db comp implemented
    result1 = RequestResult("Lib1", request)
    result2 = RequestResult("Lib2", wrong_request)
    result3 = RequestResult("Lib3", request)
    libs = evaluator.eval({result1, result2, result3}, request, log_errors=False)

    assert len(libs) == 1
    assert "Lib2" in libs


def test_logging(mock_invocation_data):
    """Test that differences are logged."""

    evaluator = DiffEvaluator()

    request = Request(
        headers=CaseInsensitiveDict({"test_header": 123}),
        body="This is a test body.",
        method=HTTPMethod.POST,
        path="/example/path",
        query_parameters={"test_parameter": 567},
    )
    wrong_request = deepcopy(request)
    request.body = "Wrong body."
    result1 = RequestResult("Lib1", request)
    result2 = RequestResult("Lib2", wrong_request)
    result3 = RequestResult("Lib3", request)
    libs = evaluator.eval({result1, result2, result3}, request, log_errors=True)

    assert len(libs) == 1
    assert len(os.listdir(evaluator.log_path)) == 1


def test_no_custom_header_diff(basic_request, mock_invocation_data):
    """Custom x-headers should not factor in evaluation."""
    request1 = deepcopy(basic_request)
    request1.headers["X-Test"] = "Test"

    request2 = deepcopy(basic_request)
    request2.headers["X-Test"] = "Othertest"

    request3 = deepcopy(request1)
    del request3.headers["X-Test"]
    request3.headers["X-Test2"] = "Test2"

    evaluator = DiffEvaluator()
    result1 = RequestResult("lib1", request1)
    result2 = RequestResult("lib2", request2)
    result3 = RequestResult("lib3", request3)
    assert not evaluator.eval({result1, result2, result3}, request1)


def test_no_header_request_comparison(basic_request, mock_invocation_data):
    """Headers should generally not be evaluated for requests."""
    request1 = deepcopy(basic_request)
    request1.headers["TestHeader"] = "Tag1"

    request2 = deepcopy(basic_request)
    request2.headers["TestHeader"] = "Tag2"

    evaluator = DiffEvaluator()
    result1 = RequestResult("lib1", request1)
    result2 = RequestResult("lib2", request2)
    result3 = RequestResult("lib3", basic_request)
    assert not evaluator.eval({result1, result2, result3}, request1)


def test_content_header_diff(basic_request, mock_invocation_data):
    """If content header in both expected and diff and different, log diff."""
    request1 = deepcopy(basic_request)
    request1.headers["Content-Type"] = "application/json"

    request2 = deepcopy(basic_request)
    if "Content-Type" in request2.headers:
        del request2.headers["Content-Type"]

    request3 = deepcopy(basic_request)
    request3.headers["Content-Type"] = "application/xml"

    evaluator = DiffEvaluator()
    result1 = RequestResult("lib1", request1)
    result2 = RequestResult("lib2", request2)
    result3 = RequestResult("lib3", request1)
    assert not evaluator.eval({result1, result2, result3}, request1)

    result3 = RequestResult("lib3", request3)
    assert evaluator.eval({result1, result2, result3}, request1) == {"lib3"}


def test_normalize_query(basic_request, mock_invocation_data):
    """Order of query parameters should not matter for evaluation."""
    original_request = deepcopy(basic_request)
    original_request.path = "/greet?age=0&name="

    eval_request = deepcopy(basic_request)
    eval_request.path = "/greet?name=&age=0"

    evaluator = DiffEvaluator()
    result = RequestResult("lib1", eval_request)

    assert not evaluator.eval({result}, original_request)


def test_normalize_json_body():
    """JSON bodies should be compared as such."""
    Config.API_CONFIG_PATH = Path("tests/testfiles/configs/api_config.yaml")

    original_request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "vsojI1",
                "Content-Type": "application/json",
                "Content-Length": "400",
            }
        ),
        body='{"age": 4800, "name": ""}',
        method=HTTPMethod.POST,
        path="/user",
        query_parameters={},
    )

    eval_request = deepcopy(original_request)
    eval_request.body = '{"name": "", "age": 4800}'

    evaluator = DiffEvaluator()
    result = RequestResult("lib1", eval_request)

    assert not evaluator.eval({result}, original_request)


def test_ignore_extra_params():
    """Test original request containing superfluous body elements."""
    Config.API_CONFIG_PATH = Path("tests/testfiles/configs/api_config.yaml")
    original_request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "localhost:8000",
                "User-Agent": "schemathesis/4.15.2",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Schemathesis-TestCaseId": "vsojI1",
                "Content-Type": "application/json",
                "Content-Length": "400",
            }
        ),
        body='{"age": 19011, "name": "dan", "c": "gone"}',
        method=HTTPMethod.POST,
        path="/user",
        query_parameters={},
    )

    eval_request = Request(
        headers=CaseInsensitiveDict(
            {
                "Host": "mitmproxy:8080",
                "User-Agent": "python-requests/2.33.1",
                "Accept-Encoding": "gzip, deflate",
                "Accept": "*/*",
                "Connection": "keep-alive",
                "Content-Length": "169",
                "Content-Type": "application/json",
            }
        ),
        body='{"name": "dan", "age": 19011}',
        method=HTTPMethod.POST,
        path="/user",
        query_parameters={},
    )

    evaluator = DiffEvaluator()
    result = RequestResult("lib1", eval_request)

    assert not evaluator.eval({result}, original_request)


def test_request_none_report(basic_request, mock_invocation_data):
    """Report should show if request was not generated."""
    original_request = basic_request
    evaluator = DiffEvaluator()
    result = RequestResult("lib1", None)

    assert evaluator.eval({result}, original_request) == set()
