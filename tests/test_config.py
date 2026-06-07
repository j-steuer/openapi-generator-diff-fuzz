"""Tests for config helper methods."""

from pathlib import Path

from telephuzz.config import Config, get_config

TEST_CONFIG_PATH = Path(__file__).parent / "testfiles" / "config.yaml"


def test_get_config():
    """Test obtaining the config and reading."""
    Config.CONFIG_PATH = TEST_CONFIG_PATH
    config = get_config()

    assert config.compose_path == "/compose/docker-compose.yaml"
    assert config.database_type == "H2"
    assert config.api_port_name == "HOST_PORT"
    assert config.port_names == ["HOST_PORT", "DB_PORT"]

    assert config.targets == [
        "openapi-generator:python",
        "swagger-codegen:python",
    ]

    assert config.timeout == 3600
