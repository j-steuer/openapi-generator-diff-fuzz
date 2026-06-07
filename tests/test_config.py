"""Tests for config helper methods."""

from pathlib import Path
from unittest.mock import mock_open, patch

import telephuzz.config as cfg
from telephuzz.config import Config, get_config

TEST_CONFIG_PATH = Path(__file__).parent / "testfiles" / "config.yaml"


def test_get_config():
    """Test obtaining the config and reading."""
    Config.CONFIG_PATH = TEST_CONFIG_PATH
    config = get_config()

    assert config.compose_path == "/compose/docker-compose.yaml"
    assert config.database_type == "H2"
    assert config.api_port_name == "HOST_PORT"
    assert config.port_names == {"HOST_PORT", "DB_PORT"}

    assert config.targets == {
        "openapi-generator:python",
        "swagger-codegen:python",
    }

    assert config.log_path == "/logs/telephuzz"
    assert config.timeout == 3600

    cfg._config = None


def test_config_singleton():
    """Test that config file is only read once."""
    with open(TEST_CONFIG_PATH, "r") as f:
        config = f.read()

    m = mock_open(read_data=config)

    with patch("builtins.open", m):
        cfg1 = cfg.get_config()
        cfg2 = cfg.get_config()

    assert cfg1 is cfg2
    assert m.call_count == 1

    cfg._config = None
