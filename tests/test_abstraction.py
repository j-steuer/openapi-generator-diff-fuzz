"""Tests for abstraction of non-deterministic values."""

import json

import pytest
from requests.models import CaseInsensitiveDict

from telephuzz.evaluation.abstractor import ABSTRACTED, Abstractor, ResponseComponent
from telephuzz.http_message import HTTPMethod, Request, Response
from telephuzz.request_result import RequestResult


def dummy_result(request: Request, response: Response) -> RequestResult:
    """Return a RequestResult object with the only relevant parts."""
    return RequestResult("", request, response, None, None)


class TestResponseComponent:
    """Unit tests for ResponseComponent."""

    def test_init_full(self):
        """Test initializing a response component with all possible fields."""
        ResponseComponent(HTTPMethod.GET, "/example", json_component="token")
        ResponseComponent(HTTPMethod.GET, "/example", regex_component=r"token*")

    def test_init_partial(self):
        """Test initializing a response component with some empty fields."""
        ResponseComponent(method=HTTPMethod.GET)
        ResponseComponent(path="/example")
        ResponseComponent(json_component="token")
        ResponseComponent(regex_component=r"token*")

    def test_init_empty(self):
        """Test initializing a response component with all empty fields."""
        with pytest.raises(ValueError, match="At least one of"):
            ResponseComponent()

    def test_init_component_conflict(self):
        """Test initializing a response component with conflicting component fields."""
        with pytest.raises(ValueError, match="At most one of"):
            ResponseComponent(json_component="token", regex_component=r"token*")


class TestAbstractor:
    """Tests for Abstractor class."""

    def test_init(self):
        """Test initializing a basic Abstractor."""
        Abstractor()

    def test_standard_headers(self, basic_request: Request, basic_response: Response):
        """Test abstraction for standard headers."""
        basic_response.headers = CaseInsensitiveDict(
            {
                "Date": "2000-01-01",
                "Etag": "Etag",
                "x-custom-header": 1,
                "content-type": "application/json",
            }
        )
        abstractor = Abstractor()
        result = dummy_result(basic_request, basic_response)

        abstractor.abstract(result)
        headers = result.response.headers

        assert headers["Date"] == ABSTRACTED
        assert headers["Etag"] == ABSTRACTED
        assert headers["x-custom-header"] == ABSTRACTED
        assert headers["content-type"] == "application/json"

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
        component = ResponseComponent(
            method=method, path=path, regex_component=regex_component
        )
        result = dummy_result(basic_request, basic_response)
        abstractor = Abstractor(custom_response_components=[component])
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
        component = ResponseComponent(
            method=method, path=path, regex_component=regex_component
        )
        result = dummy_result(basic_request, basic_response)
        abstractor = Abstractor(custom_response_components=[component])
        abstractor.abstract(result)
        assert result.response.body != ABSTRACTED

    def test_response_component_abstraction_regex(
        self, basic_request: Request, basic_response: Response
    ):
        """Test partially abstracting a response with a regex."""
        basic_response.body = "Non-deterministic-code: 1234-5678"
        component = ResponseComponent(regex_component=r"\d+-\d+")
        result = dummy_result(basic_request, basic_response)
        Abstractor(custom_response_components=[component]).abstract(result)
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
        component = ResponseComponent(json_component="Custom-Remove")
        result = dummy_result(basic_request, basic_response)
        Abstractor(custom_response_components=[component]).abstract(result)

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
