"""Tests OpenAPI helper methods"""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile, _TemporaryFileWrapper

import pytest
import yaml  # type: ignore

from telephuzz.config import get_config
from telephuzz.http_message import HTTPMethod
from telephuzz.openapi_helpers import (
    _find_all,
    extract_path_parameters,
    extract_paths,
    find_operation,
    get_api_url_path,
    get_args,
    preprocess_oas,
    resolve_path,
    resolve_request_id,
)
from telephuzz.operation_ids import generate_operation_id

OPERATION_ID = "operationId"


class TestPreprocessing:
    """Tests relating to preprocessing of OpenAPI spec files."""

    def test_preprocessing_json(self, basic_oas_json: _TemporaryFileWrapper) -> None:
        """Test insertion of custom operation ids in OpenAPI spec."""
        path = Path(basic_oas_json.name)

        with NamedTemporaryFile(mode="w+", suffix=".json") as f:
            preprocess_oas(path, Path(f.name))
            preprocessed_content = json.load(f)

        operation_ids = _find_all(preprocessed_content, OPERATION_ID)
        assert len(operation_ids) == 8

        from pprint import pprint

        pprint(preprocessed_content)

        assert isinstance(preprocessed_content, dict)
        count = 0
        for oas_path, methods in preprocessed_content.get("paths", {}).items():
            assert isinstance(methods, dict), "Methods were not loaded as a dict"
            for method, operation in methods.items():
                if OPERATION_ID in operation:
                    assert operation[OPERATION_ID] == generate_operation_id(
                        method, oas_path
                    )
                    count += 1

        assert count == len(operation_ids)

    def test_preprocessing_yaml(self, basic_oas_yaml: _TemporaryFileWrapper) -> None:
        """Test insertion of custom operation ids in OpenAPI spec."""
        path = Path(basic_oas_yaml.name)

        with NamedTemporaryFile(mode="w+", suffix=".json") as f:
            preprocess_oas(path, Path(f.name))
            preprocessed_content = yaml.safe_load(f)

        operation_ids = _find_all(preprocessed_content, OPERATION_ID)
        assert len(operation_ids) == 8

        assert isinstance(preprocessed_content, dict)
        count = 0
        for oas_path, methods in preprocessed_content.get("paths", {}).items():
            assert isinstance(methods, dict), "Methods were not loaded as a dict"
            for method, operation in methods.items():
                if OPERATION_ID in operation:
                    assert operation[OPERATION_ID] == generate_operation_id(
                        method, oas_path
                    )
                    count += 1

        assert count == len(operation_ids)


def test_find_operation(basic_oas_json: _TemporaryFileWrapper):
    """Test for finding operation based on operationId."""
    spec = json.load(basic_oas_json)

    operation = find_operation(spec, "listItems")

    assert operation is not None
    assert operation["operationId"] == "listItems"
    assert "200" in operation["responses"]


def test_find_args(monkeypatch):
    """Test finding the name of a ref arg."""
    config = get_config()

    with open("tests/testfiles/processed_petshop.json", "r") as f:
        spec = json.load(f)

    monkeypatch.setattr(config, "spec", spec)

    # concrete path should resolve
    arg = get_args(HTTPMethod.POST, "/pet")
    assert arg == "Pet"

    # non-concrete path should resolve
    arg = get_args(HTTPMethod.PUT, "/user/123")
    assert arg == "User"

    # concrete path should not resolve to non-concrete path
    arg = get_args(HTTPMethod.GET, "/user/login")
    assert arg is None

    # nonexistent path should raise error
    with pytest.raises(ValueError):
        get_args(HTTPMethod.GET, "/nonexistent")


def test_get_api_url_path_no_servers():
    """If servers are not defined, should return base path."""
    assert get_api_url_path({}) == ""


def test_get_api_url_path_no_path(spec_factory):
    """Test obtaining the api path from an OpenAPI spec if none provided."""
    spec = spec_factory(servers=[{"url": "http://localhost:8000"}])
    assert get_api_url_path(spec) == ""


def test_get_api_url_path_with_path(spec_factory):
    """Test obtaining the api path from an OpenAPI spec if none provided."""
    spec = spec_factory(servers=[{"url": "http://localhost:8000/api/v3"}])
    assert get_api_url_path(spec) == "/api/v3"


def test_extract_paths(basic_oas_json: _TemporaryFileWrapper):
    """Test extracting paths from OpenAPI spec."""
    concrete, non_concrete = extract_paths(basic_oas_json.read())
    assert concrete == {"/items"}
    assert non_concrete == {"/items/{id}"}


def test_resolve_concrete_path(basic_oas_json: _TemporaryFileWrapper):
    """Test resolving a concrete path."""
    concrete, non_concrete = extract_paths(basic_oas_json.read())

    assert (
        resolve_path("/items", concrete_paths=concrete, non_concrete_paths=non_concrete)
        == "/items"
    )


def test_resolve_non_concrete_path(basic_oas_json: _TemporaryFileWrapper):
    """Test resolving a non-concrete path."""
    concrete, non_concrete = extract_paths(basic_oas_json.read())

    assert (
        resolve_path(
            "/items/&123%", concrete_paths=concrete, non_concrete_paths=non_concrete
        )
        == "/items/{id}"
    )


def test_resolve_invalid_path(basic_oas_json: _TemporaryFileWrapper):
    """Test resolving a path that does not exist."""
    concrete, non_concrete = extract_paths(basic_oas_json.read())

    with pytest.raises(ValueError):
        resolve_path(
            "/item/&123%", concrete_paths=concrete, non_concrete_paths=non_concrete
        )


def test_resolve_request_id_concrete(basic_oas_json: _TemporaryFileWrapper):
    """Test resolving a request id with concrete path."""
    method = HTTPMethod.GET
    path = "/items"

    assert resolve_request_id(
        method, path, basic_oas_json.read()
    ) == generate_operation_id(method.value, path)


def test_resolve_request_id_non_concrete(basic_oas_json: _TemporaryFileWrapper):
    """Test resolving a request id with non-concrete path."""
    method = HTTPMethod.GET
    path = "/items/123"

    assert resolve_request_id(
        method, path, basic_oas_json.read()
    ) == generate_operation_id(method.value, "/items/{id}")


def test_extract_path_parameters():
    """Test extracting path parameters from concrete paths."""
    # should extract parameters
    assert extract_path_parameters(
        "/items/{id}/test/{name}", "/items/123/test/Test"
    ) == {"id": "123", "name": "Test"}

    # should return empty with no parameters
    assert extract_path_parameters("/items", "/items") == {}

    # should raise on mismatch
    with pytest.raises(ValueError):
        extract_path_parameters("/items", "/items/123")
