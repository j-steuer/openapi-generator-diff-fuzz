"""Tests OpenAPI helper methods"""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile, _TemporaryFileWrapper
from typing import cast

import pytest
import yaml  # type: ignore
from conftest import TEST_CONFIG_BASE_PATH

from telephuzz.config import Config, get_config
from telephuzz.http_message import HTTPMethod
from telephuzz.openapi_helpers import (
    DEFAULT_VERSION,
    RESTRICTED_MEDIA_TYPES,
    ParameterType,
    _find_all,
    build_operation_lookup,
    extract_path_parameters,
    extract_path_variable_types,
    extract_paths,
    find_operation,
    get_api_url_path,
    get_args,
    get_content_type,
    get_version,
    preprocess_oas,
    resolve_path,
    resolve_request_id,
)
from telephuzz.operation_ids import generate_operation_id

OPERATION_ID = "operationId"


class TestPreprocessing:
    """Tests relating to preprocessing of OpenAPI spec files."""

    def test_preprocessing_json(self) -> None:
        """Test insertion of custom operation ids in OpenAPI spec."""
        path = Path("wfd/openapi-swagger/swagger-petstore.json")

        with NamedTemporaryFile(mode="w+", suffix=".json") as f:
            preprocess_oas(path, Path(f.name))
            preprocessed_content = json.load(f)

        operation_ids = _find_all(preprocessed_content, OPERATION_ID)
        assert len(operation_ids) == 19

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

    def test_preprocessing_yaml(self) -> None:
        """Test insertion of custom operation ids in OpenAPI spec."""
        path = Path("wfd/openapi-swagger/swagger-petstore.json")

        with NamedTemporaryFile(mode="w+", suffix=".json") as f:
            preprocess_oas(path, Path(f.name))
            preprocessed_content = yaml.safe_load(f)

        operation_ids = _find_all(preprocessed_content, OPERATION_ID)
        assert len(operation_ids) == 19

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

    def test_restricting_media_type(self):
        """Test filtering out restricted media types."""
        processed_spec = preprocess_oas(
            Path("wfd/openapi-swagger/swagger-petstore.json")
        )
        for methods in cast(dict, processed_spec).get("paths", {}).values():
            assert isinstance(methods, dict), "Methods were not loaded as a dict"
            for operation in methods.values():
                # filter out unsupported content-types if possible
                request_body = operation.get("requestBody")
                if not isinstance(request_body, dict):
                    continue

                content = request_body.get("content")
                if not isinstance(content, dict):
                    continue

                for media_type in RESTRICTED_MEDIA_TYPES:
                    assert media_type not in content

        processed_spec = preprocess_oas(Path("wfd/openapi-swagger/quartz-manager.json"))
        login = "/quartz-manager/auth/login"
        media_type = cast(dict, processed_spec)["paths"][login]["post"]["requestBody"][
            "content"
        ]
        # should not remove if only possible content
        urlencoded = "application/x-www-form-urlencoded"
        assert urlencoded in RESTRICTED_MEDIA_TYPES
        assert urlencoded in media_type

    def test_default_version(self):
        """Version should be fixed regardless of spec."""
        processed_spec = preprocess_oas(Path("tests/testfiles/processed_petshop.json"))
        assert processed_spec is not None
        assert processed_spec["info"]["version"] == DEFAULT_VERSION


def test_find_operation(basic_oas_json: _TemporaryFileWrapper):
    """Test for finding operation based on operationId."""
    spec = json.load(basic_oas_json)

    operation = find_operation(spec, "listItems")

    assert operation is not None
    assert operation["operationId"] == "listItems"
    assert "200" in operation["responses"]


def test_find_args():
    """Test finding the name of a ref arg."""
    with open("tests/testfiles/processed_petshop.json", "r") as f:
        spec = json.dumps(json.load(f))

    # concrete path should resolve
    args = get_args(spec, HTTPMethod.POST, "/pet")
    assert args == {"requestBody": ParameterType("Pet", None, True)}

    # non-concrete path should resolve
    args = get_args(spec, HTTPMethod.PUT, "/user/123")
    assert args == {
        "requestBody": ParameterType("User", None, False),
        "username": ParameterType("string", None, True),
    }

    # concrete path should not resolve to non-concrete path
    args = get_args(spec, HTTPMethod.GET, "/user/login")
    assert args == {
        "username": ParameterType("string", None, False),
        "password": ParameterType("string", None, False),
    }

    # args that are enum should return enum as type
    args = get_args(spec, HTTPMethod.GET, "/pet/findByStatus")
    assert args == {"status": ParameterType("enum", None, False)}

    # nonexistent path should raise error
    with pytest.raises(ValueError):
        get_args(spec, HTTPMethod.GET, "/nonexistent")


def test_find_args_body_case():
    """Body case should be preserved."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"

    args = get_args(get_config().spec_str, HTTPMethod.POST, "/jobExecutions")
    assert args["requestBody"] == {"JobConfig"}


def test_find_args_no_refs():
    """Test getting all args without refs."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_http_patch_spring_config.yaml"

    args = get_args(get_config().spec_str, HTTPMethod.PATCH, "/contacts/{id}")
    assert args["requestBody"] == {"object"}


def test_get_content_type():
    """Test obtaining the content type from the spec."""
    with open("tests/testfiles/processed_petshop.json", "r") as f:
        spec = json.dumps(json.load(f))

    assert (
        get_content_type(spec, HTTPMethod.POST, "/user/createWithList")
        == "application/json"
    )

    assert get_content_type(spec, HTTPMethod.GET, "/user/login") is None


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
    assert resolve_path("/items", basic_oas_json.read()) == "/items"


def test_resolve_non_concrete_path(basic_oas_json: _TemporaryFileWrapper):
    """Test resolving a non-concrete path."""
    assert resolve_path("/items/&123%", basic_oas_json.read()) == "/items/{id}"


def test_resolve_invalid_path(basic_oas_json: _TemporaryFileWrapper):
    """Test resolving a path that does not exist."""
    with pytest.raises(ValueError):
        resolve_path("/item/&123%", basic_oas_json.read())


def test_resolve_with_path_parameters():
    """Test resolving the path ignores query parameters."""
    with open("tests/testfiles/processed_petshop.json", "r") as f:
        spec = json.dumps(json.load(f))

    path = "/pet/findByTags?tags=%C2%80%F0%A8%95%B3%F1%88%AC%93%C3%B6"
    assert resolve_path(path, spec) == "/pet/findByTags"


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


def test_extract_path_variable_types():
    """Test extracting path variable types."""
    with open("tests/testfiles/processed_petshop.json", "r") as f:
        spec = json.dumps(json.load(f))

    assert extract_path_variable_types(spec, "/pet/{petId}") == {"petId": "integer"}
    assert extract_path_variable_types(spec, "/user/{username}") == {
        "username": "string"
    }
    assert extract_path_variable_types(spec, "/user/login") == {}

    with pytest.raises(KeyError):
        extract_path_variable_types(spec, "none")


def test_get_version():
    """Test obtaining version from 2.0 and 3.x OpenAPI specs."""
    spec = {"openapi": "3.0.1"}
    assert get_version(spec) == "3.0.1"

    spec = {"swagger": "2.0"}
    assert get_version(spec) == "2.0"

    spec = {"version": "2.0"}
    with pytest.raises(ValueError):
        get_version(spec)


def test_build_operation_lookup():
    """Test building the operation lookup index from a spec."""
    with open("tests/testfiles/processed_petshop.json", "r") as f:
        spec = json.load(f)

    lookup = build_operation_lookup(spec)

    assert ("post", "/pet") in lookup
    pet_lookup = lookup[("post", "/pet")]
    assert pet_lookup["operation_id"] == generate_operation_id("POST", "/pet")
    assert pet_lookup["tag"] == "pet"
    assert lookup[("get", "/pet/{petId}")]["path"] == "/pet/{petId}"
