"""Tests for DiffFuzzer."""

import logging
import os
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

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
        body=b"This is a test body.",
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
        body=b"This is a test body.",
        method=HTTPMethod.POST,
        path="/example/path",
        query_parameters={"test_parameter": 567},
    )
    wrong_request = deepcopy(request)
    request.body = b"Wrong body."
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
        body=b"This is a test body.",
        method=HTTPMethod.POST,
        path="/example/path",
        query_parameters={"test_parameter": 567},
    )
    wrong_request = deepcopy(request)
    request.body = b"Wrong body."
    result1 = RequestResult("Lib1", request)
    result2 = RequestResult("Lib2", wrong_request)
    result3 = RequestResult("Lib3", request)
    libs = evaluator.eval({result1, result2, result3}, request, log_errors=True)

    assert len(libs) == 1
    assert len(os.listdir(evaluator.log_path)) == 1


def test_no_custom_header_diff(basic_request, mock_invocation_data, caplog):
    """Custom x-headers should not factor in evaluation."""
    caplog.set_level("DEBUG")
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

    assert "Different headers" in caplog.text


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
        body=b'{"age": 4800, "name": ""}',
        method=HTTPMethod.POST,
        path="/user",
        query_parameters={},
    )

    eval_request = deepcopy(original_request)
    eval_request.body = b'{"name": "", "age": 4800}'

    evaluator = DiffEvaluator()
    result = RequestResult("lib1", eval_request)

    assert not evaluator.eval({result}, original_request)


def test_json_value_diff():
    """Test detail when value of JSON element differs."""
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
        body=b'{"age": 4800, "name": ""}',
        method=HTTPMethod.POST,
        path="/user",
        query_parameters={},
    )

    eval_request = deepcopy(original_request)
    eval_request.body = b'{"name": "", "age": 4801}'

    evaluator = DiffEvaluator()
    result = RequestResult("lib1", eval_request)

    with patch("telephuzz.evaluation.evaluator.DiffReport") as mock_report:
        assert evaluator.eval({result}, original_request) == {"lib1"}

        mock_report.assert_called_once()
        kwargs = mock_report.call_args.kwargs

        assert (
            "Unequal values for element 'age' in body: 4800 != 4801" in kwargs["detail"]
        )


def test_json_element_diff():
    """Test detail when element only exists in original."""
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
        body=b'{"age": 4800, "name": ""}',
        method=HTTPMethod.POST,
        path="/user",
        query_parameters={},
    )

    eval_request = deepcopy(original_request)
    eval_request.body = b'{"name": ""}'

    evaluator = DiffEvaluator()
    result = RequestResult("lib1", eval_request)

    with patch("telephuzz.evaluation.evaluator.DiffReport") as mock_report:
        assert evaluator.eval({result}, original_request) == {"lib1"}

        mock_report.assert_called_once()
        kwargs = mock_report.call_args.kwargs

        assert "Element 'age' only exists in original body" in kwargs["detail"]


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
        body=b'{"age": 19011, "name": "dan", "c": "gone"}',
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
        body=b'{"name": "dan", "age": 19011}',
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


def test_semantically_equivalent_datetime(tmp_path, caplog):
    """Special message for only syntactically different date-time."""
    caplog.set_level(logging.DEBUG)
    Config.API_CONFIG_PATH = Path("tests/testfiles/configs/api_petshop_config.yaml")
    request1 = Request(
        headers=CaseInsensitiveDict(
            {
                "Content-Type": "application/json",
                "Accept": "application/json",
            }
        ),
        body=(
            b'{"id":1,'
            b'"petId":10,'
            b'"quantity":1,'
            b'"shipDate":"7861-04-29T22:31:12.387165Z",'
            b'"status":"placed",'
            b'"complete":false}'
        ),
        method=HTTPMethod.POST,
        path="/store/order",
        query_parameters={},
    )

    request2 = deepcopy(request1)
    request2.body = (
        b'{"id":1,'
        b'"petId":10,'
        b'"quantity":1,'
        b'"shipDate":"7861-04-29T22:31:12.387165+00:00",'
        b'"status":"placed",'
        b'"complete":false}'
    )

    evaluator = DiffEvaluator()
    evaluator.log_path = tmp_path

    result = RequestResult("lib1", request2)
    assert not evaluator.eval({result}, request1)
    assert len(os.listdir(tmp_path)) == 0

    # semantic differences should still be reported
    assert result.request is not None
    assert result.request.body is not None
    result.request.body = result.request.body.replace(b'"id":1', b'"id":2')
    assert evaluator.eval({result}, request1) == {"lib1"}
    assert len(os.listdir(tmp_path)) == 1

    assert "Syntactically different but semantically equivalent date" in caplog.text


def test_invalid_path(tmp_path, caplog):
    """Invalid paths should also result in report."""
    Config.API_CONFIG_PATH = Path("tests/testfiles/configs/api_petshop_config.yaml")
    caplog.set_level(logging.DEBUG)

    request1 = Request(
        headers=CaseInsensitiveDict(),
        body=b"",
        method=HTTPMethod.GET,
        path="/user/.",
        query_parameters={},
    )

    request2 = deepcopy(request1)
    request2.path = "/user/"

    result = RequestResult("lib1", request2)

    evaluator = DiffEvaluator()
    evaluator.log_path = tmp_path
    assert evaluator.eval({result}, request1) == {"lib1"}

    assert len(os.listdir(tmp_path)) == 1
    assert "Error while creating invocation for result" in caplog.text
