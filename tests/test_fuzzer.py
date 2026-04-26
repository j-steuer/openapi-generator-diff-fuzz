"""Tests relating to fuzzer.py."""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile, _TemporaryFileWrapper
from typing import Any

import yaml  # type: ignore

from telephuzz.fuzzer import TelePhuzz

OPERATION_ID = "operation_id"


def _find_all(spec: dict, element: str) -> list[Any]:
    """Find all instances of element in the spec."""
    results = []

    if isinstance(spec, dict):
        for k, v in spec.items():
            if k == element:
                results.append(v)
            else:
                results.extend(_find_all(v, element))

    return results


class TestPreprocessing:
    """Tests relating to preprocessing of OpenAPI spec files."""

    def test_preprocessing_json(self, basic_oas_json: _TemporaryFileWrapper) -> None:
        """Test insertion of custom operation ids in OpenAPI spec."""
        path = Path(basic_oas_json.name)
        fuzzer = TelePhuzz(path)

        with NamedTemporaryFile(mode="w+", suffix=".json") as f:
            fuzzer._preprocess_oas(path, Path(f.name))
            preprocessed_content = json.load(f)

        operation_ids = _find_all(preprocessed_content, OPERATION_ID)
        assert len(operation_ids) == 8

        assert isinstance(preprocessed_content, dict)
        count = 0
        for oas_path, methods in preprocessed_content.get("paths", {}).items():
            assert isinstance(methods, dict), "Methods were not loaded as a dict"
            for method, operation in methods.items():
                if OPERATION_ID in operation:
                    assert operation[OPERATION_ID] == fuzzer._get_operation_id(
                        method, oas_path
                    )
                    count += 1

        assert count == len(operation_ids)

    def test_preprocessing_yaml(self, basic_oas_yaml: _TemporaryFileWrapper) -> None:
        """Test insertion of custom operation ids in OpenAPI spec."""
        path = Path(basic_oas_yaml.name)
        fuzzer = TelePhuzz(path)

        with NamedTemporaryFile(mode="w+", suffix=".json") as f:
            fuzzer._preprocess_oas(path, Path(f.name))
            preprocessed_content = yaml.safe_load(f)

        operation_ids = _find_all(preprocessed_content, OPERATION_ID)
        assert len(operation_ids) == 8

        assert isinstance(preprocessed_content, dict)
        count = 0
        for oas_path, methods in preprocessed_content.get("paths", {}).items():
            assert isinstance(methods, dict), "Methods were not loaded as a dict"
            for method, operation in methods.items():
                if OPERATION_ID in operation:
                    assert operation[OPERATION_ID] == fuzzer._get_operation_id(
                        method, oas_path
                    )
                    count += 1

        assert count == len(operation_ids)

    def test_preprocessing_collision(self, basic_oas_json) -> None:
        """Test that there is no collision with parameter and literal path names."""
        fuzzer = TelePhuzz(basic_oas_json)
        method = "GET"
        base_path = "/test"
        assert fuzzer._get_operation_id(
            method, f"{base_path}/id"
        ) != fuzzer._get_operation_id(method, f"{base_path}/{{id}}")

    def test_deterministic_operation_id(self, basic_oas_json) -> None:
        """Obtaining the operation id should be deterministic."""
        fuzzer = TelePhuzz(basic_oas_json)
        method = "GET"
        path = "/test/{id}"

        assert fuzzer._get_operation_id(method, path) == fuzzer._get_operation_id(
            method, path
        )

        fuzzer2 = TelePhuzz(basic_oas_json)
        assert fuzzer._get_operation_id(method, path) == fuzzer2._get_operation_id(
            method, path
        )
