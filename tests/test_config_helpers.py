"""Tests for config helper methods."""

from pathlib import Path

import telephuzz.config_helpers

TEST_CONFIG_PATH = Path(__file__).parent / "testfiles" / "config.yaml"


def test_get_config(monkeypatch):
    """Test obtaining the config and reading values."""
    monkeypatch.setattr(telephuzz.config_helpers, "CONFIG_PATH", TEST_CONFIG_PATH)
    config = telephuzz.config_helpers.get_config()

    assert config["api"]["compose-path"] == "/compose/docker-compose.yaml"
    assert config["api"]["database-type"] == "H2"
    assert config["api"]["api-port-name"] == "HOST_PORT"
    assert config["api"]["port-names"] == ["HOST_PORT", "DB_PORT"]

    assert config["targets"] == [
        "openapi-generator:python",
        "swagger-codegen:python",
    ]

    assert config["fuzzing"]["timeout"] == 3600
