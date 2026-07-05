"""Tests for config helper methods."""

import telephuzz.config as cfg
from telephuzz.config import get_config


def test_get_config():
    """Test obtaining the config and reading."""
    config = get_config()

    assert config.api_container_name == "api"
    assert config.compose_path == "/compose/docker-compose.yaml"
    assert config.spec
    assert config.spec_str
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
