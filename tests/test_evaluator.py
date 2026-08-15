"""Tests for DiffFuzzer."""

import os
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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
        content_type="text/plain",
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
        content_type="text/plain",
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
        content_type="text/plain",
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


def test_content_header_diff():
    """If content header in both expected and diff and different, log diff."""
    Config.API_CONFIG_PATH = Path("tests/testfiles/configs/api_config.yaml")

    original_request = Request(
        content_type="application/json",
        body=b'{"age": 4800, "name": ""}',
        method=HTTPMethod.POST,
        path="/user",
        query_parameters={},
    )
    request1 = deepcopy(original_request)

    request2 = deepcopy(original_request)
    request2.content_type = None

    request3 = deepcopy(original_request)
    request3.content_type = "application/xml"

    evaluator = DiffEvaluator()
    result1 = RequestResult("lib1", request1)
    result2 = RequestResult("lib2", request2)
    result3 = RequestResult("lib3", request1)
    assert not evaluator.eval({result1, result2, result3}, request1)

    result3 = RequestResult("lib3", request3)
    assert evaluator.eval({result1, result2, result3}, request1) == {"lib3"}


def test_ignore_original_content_header_if_empty():
    """Do not log error if original content header is empty."""
    Config.API_CONFIG_PATH = Path("tests/testfiles/configs/api_petshop_config.yaml")

    original_request = Request(
        content_type=None,
        body=b"",
        method=HTTPMethod.GET,
        path="/pet/findByTags?tags=L&tags=9&tags=",
        query_parameters={"tags": ["L", "9", ""]},
    )

    request2 = deepcopy(original_request)
    request2.content_type = "application/json"

    evaluator = DiffEvaluator()
    result2 = RequestResult("lib2", request2)

    with patch("telephuzz.evaluation.evaluator.DiffReport") as mock_report:
        assert not evaluator.eval({result2}, original_request)
        mock_report.assert_not_called()


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
        content_type="application/json",
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
        content_type="application/json",
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
        content_type="application/json",
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
        content_type="application/json",
        body=b'{"age": 19011, "name": "dan", "c": "gone"}',
        method=HTTPMethod.POST,
        path="/user",
        query_parameters={},
    )

    eval_request = Request(
        content_type="application/json",
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
