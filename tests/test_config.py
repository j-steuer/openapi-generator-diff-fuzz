"""Tests for config helper methods."""

from conftest import TEST_CONFIG_BASE_PATH

import telephuzz.config as cfg
from telephuzz.config import Config, get_config
from telephuzz.evaluation.nondeterministic_component import NondeterministicComponent
from telephuzz.http_message import HTTPMethod


def test_get_config():
    """Test obtaining the config and reading."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_config_ndt_components.yaml"
    config = get_config()

    assert config.api_container_name == "api"
    assert config.compose_path == "/compose/docker-compose.yaml"
    assert config.spec
    assert config.spec_str
    assert config.database_type == "H2"
    assert config.api_port_name == "HOST_PORT"
    assert config.port_names == {"HOST_PORT", "DB_PORT"}

    ndt_components = config.nondeterministic_components
    assert_components = [
        NondeterministicComponent(method=HTTPMethod.GET),
        NondeterministicComponent(path="/login"),
        NondeterministicComponent(
            method=HTTPMethod.POST, path="/login", json_component="access_token"
        ),
        NondeterministicComponent(regex_component=r"Bearer\s+\S+"),
        NondeterministicComponent(json_component="id"),
    ]
    for c in assert_components:
        assert c in ndt_components

    assert len(config.targets) == 2
    assert config.targets["openapi-generator:python"] == "openapi-gen-python-client"
    assert config.targets["swagger-codegen:python"] == "swagger-codegen-python-client"

    assert config.log_path == "/tmp/logs/telephuzz"
    assert config.timeout == 3600

    cfg._config = None
