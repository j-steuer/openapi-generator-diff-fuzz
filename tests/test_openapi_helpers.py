"""Tests OpenAPI helper methods"""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile, _TemporaryFileWrapper

import yaml  # type: ignore

from telephuzz.openapi_helpers import _find_all, preprocess_oas
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
