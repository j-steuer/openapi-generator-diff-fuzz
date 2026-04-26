"""Tests relating to fuzzer.py."""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile, _TemporaryFileWrapper
from typing import Any

import yaml  # type: ignore

from telephuzz.fuzzer import TelePhuzz


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


class TestPreprocessing:  # TODO add checks for content, correct names, collision, etc.
    """Tests relating to preprocessing of OpenAPI spec files."""

    def test_preprocessing_json(self, basic_oas_json: _TemporaryFileWrapper) -> None:
        """Test insertion of custom operation ids in OpenAPI spec."""
        path = Path(basic_oas_json.name)
        fuzzer = TelePhuzz(path)

        with NamedTemporaryFile(mode="w+", suffix=".json") as f:
            fuzzer._preprocess_oas(path, Path(f.name))
            preprocessed_content = json.load(f)

        operation_ids = _find_all(preprocessed_content, "operation_id")
        assert len(operation_ids) == 8

    def test_preprocessing_yaml(self, basic_oas_yaml: _TemporaryFileWrapper) -> None:
        """Test insertion of custom operation ids in OpenAPI spec."""
        path = Path(basic_oas_yaml.name)
        fuzzer = TelePhuzz(path)

        with NamedTemporaryFile(mode="w+", suffix=".json") as f:
            fuzzer._preprocess_oas(path, Path(f.name))
            preprocessed_content = yaml.safe_load(f)

        operation_ids = _find_all(preprocessed_content, "operation_id")
        assert len(operation_ids) == 8
