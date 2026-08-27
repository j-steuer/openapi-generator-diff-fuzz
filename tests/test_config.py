"""Tests for config helper methods."""

import pytest
from conftest import TEST_CONFIG_BASE_PATH

import telephuzz.config as cfg
from telephuzz.config import Config, get_config
from telephuzz.evaluation.nondeterministic_component import NondeterministicComponent
from telephuzz.http_message import HTTPMethod
from telephuzz.operation_ids import generate_operation_id


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

    cfg._config = None


def test_operation_id_lookup() -> None:
    """Test the operation_id_lookup method."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    config = get_config()

    # Test a known operation
    method = "GET"
    path = "/user/login"
    operation_id = config.operation_id_lookup(method, path)
    assert operation_id == generate_operation_id(method, path)

    # Test an unknown operation
    method = "POST"
    path = "/unknown"
    with pytest.raises(ValueError):
        config.operation_id_lookup(method, path)


def test_tag_lookup() -> None:
    """Test the tag_lookup method."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"
    config = get_config()

    # Test a known tag
    method = "GET"
    path = "/jobs"
    tag = config.tag_lookup(method, path)
    assert tag == "job-controller"

    # Test an unknown tag
    method = "POST"
    path = "/unknown"
    with pytest.raises(ValueError):
        config.tag_lookup(method, path)


def test_jacoco() -> None:
    """Test loading jacoco data."""
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"
    config = get_config()

    assert config.jacoco_port == 6300
    assert config.jacoco_path == "./reports/coverage/api_springbatch_config"
