"""Tests for abstraction of non-deterministic values."""

import json

import pytest
from requests.models import CaseInsensitiveDict

from telephuzz.evaluation.abstractor import (
    ABSTRACTED,
    Abstractor,
)
from telephuzz.evaluation.nondeterministic_component import NondeterministicComponent
from telephuzz.http_message import HTTPMethod, Request, Response
from telephuzz.request_result import RequestResult


def dummy_result(request: Request, response: Response) -> RequestResult:
    """Return a RequestResult object with the only relevant parts."""
    return RequestResult("", request, response, None, None)


class TestNondeterministicComponent:
    """Unit tests for NondeterministicComponent."""

    def test_init_full(self):
        """Test initializing a component with all possible fields."""
        NondeterministicComponent(HTTPMethod.GET, "/example", json_component="token")
        NondeterministicComponent(HTTPMethod.GET, "/example", regex_component=r"token*")

    def test_init_partial(self):
        """Test initializing a component with some empty fields."""
        NondeterministicComponent(method=HTTPMethod.GET)
        NondeterministicComponent(path="/example")
        NondeterministicComponent(json_component="token")
        NondeterministicComponent(regex_component=r"token*")

    def test_init_empty(self):
        """Test initializing a component with all empty fields."""
        with pytest.raises(ValueError, match="At least one of"):
            NondeterministicComponent()

    def test_init_component_conflict(self):
        """Test initializing a component with conflicting fields."""
        with pytest.raises(ValueError, match="At most one of"):
            NondeterministicComponent(json_component="token", regex_component=r"token*")


class TestAbstractor:
    """Tests for Abstractor class."""

    def test_init(self):
        """Test initializing a basic Abstractor."""
        Abstractor()

    def test_standard_headers(self, basic_request: Request, basic_response: Response):
        """Test abstraction for standard headers."""
        basic_request.headers = CaseInsensitiveDict(
            {
                "Date": "2000-01-01",
                "Etag": "Etag",
                "x-custom-header": 1,
                "X-Test-Header": 2,
                "content-type": "application/json",
            }
        )

        basic_response.headers = CaseInsensitiveDict(
            {
                "Date": "2000-01-01",
                "Etag": "Etag",
                "x-custom-header": 1,
                "X-Test-Header": 2,
                "content-type": "application/json",
            }
        )
        abstractor = Abstractor()
        result = dummy_result(basic_request, basic_response)

        abstractor.abstract(result)
        request_headers = result.request.headers
        response_headers = result.response.headers

        assert "Date" not in request_headers
        assert "Etag" not in request_headers
        assert "x-custom-header" not in request_headers
        assert "X-Test-Header" not in request_headers
        assert request_headers["content-type"] == "application/json"

        assert response_headers["Date"] == ABSTRACTED
        assert response_headers["Etag"] == ABSTRACTED
        assert response_headers["x-custom-header"] == ABSTRACTED
        assert response_headers["X-Test-Header"] == ABSTRACTED
        assert response_headers["content-type"] == "application/json"

    @pytest.mark.parametrize(
        "method, path, regex_component",
        [
            (HTTPMethod.GET, "/example", r"This is a response."),
            (HTTPMethod.GET, "/example", None),
            (HTTPMethod.GET, None, r"This is a response."),
            (None, "/example", r"This is a response."),
            (HTTPMethod.GET, None, None),
            (None, "/example", None),
            (None, None, r"This is a response."),
        ],
    )
    def test_response_component_abstraction_full(
        self,
        basic_request: Request,
        basic_response: Response,
        method,
        path,
        regex_component,
    ):
        """Test cases where response component should fully abstract."""
        basic_request.method = HTTPMethod.GET
        basic_request.path = "/example"
        basic_response.body = "This is a response."
        component = NondeterministicComponent(
            method=method, path=path, regex_component=regex_component
        )
        result = dummy_result(basic_request, basic_response)
        abstractor = Abstractor(custom_ndt_components=[component])
        abstractor.abstract(result)
        assert result.response.body == ABSTRACTED

    @pytest.mark.parametrize(
        "method, path, regex_component",
        [
            (HTTPMethod.POST, "/example", r"This is a response."),
            (HTTPMethod.GET, "/path", r"This is a response."),
            (HTTPMethod.GET, "/path", r"NotFound"),
        ],
    )
    def test_response_component_no_abstraction(
        self,
        basic_request: Request,
        basic_response: Response,
        method,
        path,
        regex_component,
    ):
        """Test cases where response component should not abstract."""
        basic_request.method = HTTPMethod.GET
        basic_request.path = "/example"
        basic_response.body = "This is a response."
        component = NondeterministicComponent(
            method=method, path=path, regex_component=regex_component
        )
        result = dummy_result(basic_request, basic_response)
        abstractor = Abstractor(custom_ndt_components=[component])
        abstractor.abstract(result)
        assert result.response.body != ABSTRACTED

    def test_response_component_abstraction_regex(
        self, basic_request: Request, basic_response: Response
    ):
        """Test partially abstracting a response with a regex."""
        basic_response.body = "Non-deterministic-code: 1234-5678"
        component = NondeterministicComponent(regex_component=r"\d+-\d+")
        result = dummy_result(basic_request, basic_response)
        Abstractor(custom_ndt_components=[component]).abstract(result)
        assert result.response.body == f"Non-deterministic-code: {ABSTRACTED}"

    def test_response_component_abstraction_json(
        self, basic_request: Request, basic_response: Response
    ):
        """Test abstracting a JSON response field."""
        json_response = json.dumps(
            {
                "level1": {
                    "level2": {"Custom-Remove": "this value should be removed"},
                    "other_key": 123,
                },
                "another_top_level": {"keep_me": True},
            }
        )
        basic_response.body = json_response
        component = NondeterministicComponent(json_component="Custom-Remove")
        result = dummy_result(basic_request, basic_response)
        Abstractor(custom_ndt_components=[component]).abstract(result)

        abstracted_json_response = json.loads(result.response.body)
        assert (
            abstracted_json_response["level1"]["level2"]["Custom-Remove"] == ABSTRACTED
        )
        assert abstracted_json_response["level1"]["other_key"] == 123
        assert str(abstracted_json_response["another_top_level"]["keep_me"]) == "True"

    def test_custom_header(self, basic_request: Request, basic_response: Response):
        """Test abstracting custom defined headers."""
        basic_response.headers = CaseInsensitiveDict(
            {"Date": "2000-01-01", "Custom-Remove": 1, "Custom-Keep": 1}
        )
        result = dummy_result(basic_request, basic_response)
        Abstractor(custom_headers=["Custom-Remove"]).abstract(result)

        headers = result.response.headers
        assert headers["Date"] == ABSTRACTED
        assert headers["Custom-Remove"] == ABSTRACTED
        assert headers["Custom-Keep"] == 1

    def test_config_components(self, basic_request: Request, basic_response: Response):
        """Test abstracting values defined in the config."""
        basic_request.method = HTTPMethod.GET
        basic_request.path = "/test/random"

        json_response = json.dumps(
            {
                "level1": {
                    "level2": {"Custom": "1"},
                    "other_key": 123,
                    "random": "234",
                },
                "random": "1234",
            }
        )

        basic_response.body = json_response

        result = dummy_result(basic_request, basic_response)

        abstractor = Abstractor()
        assert (
            NondeterministicComponent(
                method=HTTPMethod.GET, path="/test/random", json_component="random"
            )
            in abstractor.custom_ndt_components
        ), abstractor.custom_ndt_components

        abstractor.abstract(result)
        abstracted_json_response = json.loads(result.response.body)
        assert abstracted_json_response["random"] == ABSTRACTED
        assert abstracted_json_response["level1"]["random"] == ABSTRACTED

    def test_ignore_query_parameters(
        self, basic_request: Request, basic_response: Response
    ):
        """Abstractors should ignore query parameters in the path."""
        basic_request.method = HTTPMethod.GET
        basic_request.path = "/test/random?somevalue=100"

        json_response = json.dumps(
            {
                "level1": {
                    "level2": {"Custom": "1"},
                    "other_key": 123,
                    "random": "234",
                },
                "random": "1234",
            }
        )

        basic_response.body = json_response

        result = dummy_result(basic_request, basic_response)

        abstractor = Abstractor()
        assert (
            NondeterministicComponent(
                method=HTTPMethod.GET, path="/test/random", json_component="random"
            )
            in abstractor.custom_ndt_components
        ), abstractor.custom_ndt_components

        abstractor.abstract(result)
        abstracted_json_response = json.loads(result.response.body)
        assert abstracted_json_response["random"] == ABSTRACTED
        assert abstracted_json_response["level1"]["random"] == ABSTRACTED
