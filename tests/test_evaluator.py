"""Tests for DiffFuzzer."""

import os
from copy import deepcopy

from requests.models import CaseInsensitiveDict

from telephuzz.evaluation.evaluator import DiffEvaluator
from telephuzz.http_message import HTTPMethod, Request, Response
from telephuzz.request_result import RequestResult


def test_same_request_responses():
    """Test that DiffFuzzer returns an empty set if no diffs."""
    evaluator = DiffEvaluator()

    request = Request(
        headers=CaseInsensitiveDict({"test_header": 123}),
        body="This is a test body.",
        method=HTTPMethod.POST,
        path="/example/path",
        query_parameters={"test_parameter": 567},
    )
    response = Response(
        headers=CaseInsensitiveDict({"response_header": "test"}),
        body="This is a response body.",
        status=404,
    )
    # TODO adjust when db comp implemented
    result1 = RequestResult("Lib1", request, response, None, None)
    result2 = RequestResult("Lib2", request, response, None, None)
    result3 = RequestResult("Lib3", request, response, None, None)
    libs = evaluator.eval({result1, result2, result3}, request, log_errors=False)

    assert len(libs) == 0


def test_same_diff_request():
    """Test that DiffFuzzer recognizes a diff in requests and returns the library."""
    evaluator = DiffEvaluator()

    request = Request(
        headers=CaseInsensitiveDict({"test_header": 123}),
        body="This is a test body.",
        method=HTTPMethod.POST,
        path="/example/path",
        query_parameters={"test_parameter": 567},
    )
    response = Response(
        headers=CaseInsensitiveDict({"response_header": "test"}),
        body="This is a response body.",
        status=404,
    )
    wrong_request = deepcopy(request)
    request.body = "Wrong body."
    # TODO adjust when db comp implemented
    result1 = RequestResult("Lib1", request, response, None, None)
    result2 = RequestResult("Lib2", wrong_request, response, None, None)
    result3 = RequestResult("Lib3", request, response, None, None)
    libs = evaluator.eval({result1, result2, result3}, request, log_errors=False)

    assert len(libs) == 1
    assert "Lib2" in libs


def test_same_diff_response():
    """Test that DiffFuzzer recognizes a diff in responses and returns the library."""
    evaluator = DiffEvaluator()

    request = Request(
        headers=CaseInsensitiveDict({"test_header": 123}),
        body="This is a test body.",
        method=HTTPMethod.POST,
        path="/example/path",
        query_parameters={"test_parameter": 567},
    )
    response = Response(
        headers=CaseInsensitiveDict({"response_header": "test"}),
        body="This is a response body.",
        status=404,
    )
    wrong_response = deepcopy(response)
    wrong_response.body = "Wrong body."
    # TODO adjust when db comp implemented
    result1 = RequestResult("Lib1", request, response, None, None)
    result2 = RequestResult("Lib2", request, wrong_response, None, None)
    result3 = RequestResult("Lib3", request, response, None, None)
    libs = evaluator.eval({result1, result2, result3}, request, log_errors=False)

    assert len(libs) == 1
    assert "Lib2" in libs


def test_logging():
    """Test that differences are logged."""

    evaluator = DiffEvaluator()

    request = Request(
        headers=CaseInsensitiveDict({"test_header": 123}),
        body="This is a test body.",
        method=HTTPMethod.POST,
        path="/example/path",
        query_parameters={"test_parameter": 567},
    )
    response = Response(
        headers=CaseInsensitiveDict({"response_header": "test"}),
        body="This is a response body.",
        status=404,
    )
    wrong_request = deepcopy(request)
    request.body = "Wrong body."
    result1 = RequestResult("Lib1", request, response, None, None)
    result2 = RequestResult("Lib2", wrong_request, response, None, None)
    result3 = RequestResult("Lib3", request, response, None, None)
    libs = evaluator.eval({result1, result2, result3}, request, log_errors=True)

    assert len(libs) == 1
    assert len(os.listdir(evaluator.log_path)) == 1


def test_no_custom_header_diff(basic_request, basic_response):
    """Custom x-headers should not factor in evaluation."""
    request1 = deepcopy(basic_request)
    request1.headers["X-Test"] = "Test"

    request2 = deepcopy(basic_request)
    request2.headers["X-Test"] = "Othertest"

    request3 = deepcopy(request1)
    del request3.headers["X-Test"]
    request3.headers["X-Test2"] = "Test2"

    evaluator = DiffEvaluator()
    result1 = RequestResult("lib1", request1, basic_response, None, None)
    result2 = RequestResult("lib2", request2, basic_response, None, None)
    result3 = RequestResult("lib3", request3, basic_response, None, None)
    assert not evaluator.eval({result1, result2, result3}, request1)


def test_no_header_request_comparison(basic_request, basic_response):
    """Headers should generally not be evaluated for requests."""
    request1 = deepcopy(basic_request)
    request1.headers["TestHeader"] = "Tag1"

    request2 = deepcopy(basic_request)
    request2.headers["TestHeader"] = "Tag2"

    evaluator = DiffEvaluator()
    result1 = RequestResult("lib1", request1, basic_response, None, None)
    result2 = RequestResult("lib2", request2, basic_response, None, None)
    result3 = RequestResult("lib3", basic_request, basic_response, None, None)
    assert not evaluator.eval({result1, result2, result3}, request1)


def test_content_header_diff(basic_request, basic_response):
    """If content header in both expected and diff and different, log diff."""
    request1 = deepcopy(basic_request)
    request1.headers["Content-Type"] = "application/json"

    request2 = deepcopy(basic_request)
    if "Content-Type" in request2.headers:
        del request2.headers["Content-Type"]

    request3 = deepcopy(basic_request)
    request3.headers["Content-Type"] = "application/xml"

    evaluator = DiffEvaluator()
    result1 = RequestResult("lib1", request1, basic_response, None, None)
    result2 = RequestResult("lib2", request2, basic_response, None, None)
    result3 = RequestResult("lib3", request1, basic_response, None, None)
    assert not evaluator.eval({result1, result2, result3}, request1)

    result2 = RequestResult("lib2", request1, basic_response, None, None)
    result3 = RequestResult("lib3", request3, basic_response, None, None)
    assert evaluator.eval({result1, result2, result3}, request1) == {"lib3"}
