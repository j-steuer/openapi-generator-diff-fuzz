"""Tests for config helper methods."""

from unittest.mock import mock_open, patch

from conftest import TEST_CONFIG_PATH

import telephuzz.config as cfg
from telephuzz.config import get_config


def test_get_config():
    """Test obtaining the config and reading."""
    config = get_config()

    assert config.compose_path == "/compose/docker-compose.yaml"
    assert config.database_type == "H2"
    assert config.api_port_name == "HOST_PORT"
    assert config.port_names == {"HOST_PORT", "DB_PORT"}
    assert config.nondeterministic_fields == {
        "POST": {"/test/example": {"timestamp", "token"}},
        "GET": {"/test/random": {"random"}},
    }

    assert len(config.targets) == 2
    assert config.targets["openapi-generator:python"] == "openapi-gen-python-client"
    assert config.targets["swagger-codegen:python"] == "swagger-codegen-python-client"

    assert config.log_path == "/tmp/logs/telephuzz"
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
