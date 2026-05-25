"""Tests for DiffFuzzer."""

from copy import deepcopy
from pathlib import Path

from requests.models import CaseInsensitiveDict

from telephuzz.evaluation.evaluator import DiffEvaluator
from telephuzz.http_message import HTTPMethod, Request, Response
from telephuzz.request_result import RequestResult


def test_same_request_responses():
    """Test that DiffFuzzer returns an empty set if no diffs."""
    evaluator = DiffEvaluator(Path(""))

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
        text="Not found.",
    )
    # TODO adjust when db comp implemented
    result1 = RequestResult("Lib1", request, response, Path(""), Path(""))
    result2 = RequestResult("Lib2", request, response, Path(""), Path(""))
    result3 = RequestResult("Lib3", request, response, Path(""), Path(""))
    libs = evaluator.eval([result1, result2, result3], request, log_errors=False)

    assert len(libs) == 0


def test_same_diff_request():
    """Test that DiffFuzzer recognizes a diff in requests and returns the library."""
    evaluator = DiffEvaluator(Path(""))

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
        text="Not found.",
    )
    wrong_request = deepcopy(request)
    request.body = "Wrong body."
    # TODO adjust when db comp implemented
    result1 = RequestResult("Lib1", request, response, Path(""), Path(""))
    result2 = RequestResult("Lib2", wrong_request, response, Path(""), Path(""))
    result3 = RequestResult("Lib3", request, response, Path(""), Path(""))
    libs = evaluator.eval([result1, result2, result3], request, log_errors=False)

    assert len(libs) == 1
    assert "Lib2" in libs


def test_same_diff_response():
    """Test that DiffFuzzer recognizes a diff in responses and returns the library."""
    evaluator = DiffEvaluator(Path(""))

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
        text="Not found.",
    )
    wrong_response = deepcopy(response)
    wrong_response.body = "Wrong body."
    # TODO adjust when db comp implemented
    result1 = RequestResult("Lib1", request, response, Path(""), Path(""))
    result2 = RequestResult("Lib2", request, wrong_response, Path(""), Path(""))
    result3 = RequestResult("Lib3", request, response, Path(""), Path(""))
    libs = evaluator.eval([result1, result2, result3], request, log_errors=False)

    assert len(libs) == 1
    assert "Lib2" in libs
