"""Tests OpenAPI helper methods"""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile, _TemporaryFileWrapper
from unittest.mock import patch

import yaml  # type: ignore

from telephuzz.config import get_config
from telephuzz.http_message import HTTPMethod
from telephuzz.openapi_helpers import (
    _find_all,
    find_operation,
    get_args,
    preprocess_oas,
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


def test_find_args():
    """Test finding the name of a ref arg."""
    spec = {
        "post": {
            "tags": ["pet"],
            "summary": "Add a new pet to the store.",
            "description": "Add a new pet to the store.",
            "operationId": "post_pet_cec649da",
            "requestBody": {
                "description": "Create a new pet in the store",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/Pet"}
                    },
                    "application/xml": {"schema": {"$ref": "#/components/schemas/Pet"}},
                    "application/x-www-form-urlencoded": {
                        "schema": {"$ref": "#/components/schemas/Pet"}
                    },
                },
                "required": True,
            },
            "responses": {
                "200": {
                    "description": "Successful operation",
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/Pet"}
                        },
                        "application/xml": {
                            "schema": {"$ref": "#/components/schemas/Pet"}
                        },
                    },
                },
                "400": {"description": "Invalid input"},
                "422": {"description": "Validation exception"},
                "default": {"description": "Unexpected error"},
            },
            "security": [{"petstore_auth": ["write:pets", "read:pets"]}],
        }
    }

    with patch.object(get_config(), "spec", spec):
        arg = get_args(HTTPMethod.POST, "/pet")
        assert arg == "Pet"
