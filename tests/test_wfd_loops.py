"""Tests for full fuzzing loops with WFD APIs."""

from conftest import TEST_CONFIG_BASE_PATH

from telephuzz.config import Config
from telephuzz.fuzzer import TelePhuzz


def test_python_petshop() -> None:
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_python_config.yaml"

    fuzzer = TelePhuzz()
    fuzzer.start_fuzzing_session()


def test_python_springbatch() -> None:
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_python_config.yaml"

    fuzzer = TelePhuzz()
    fuzzer.start_fuzzing_session()


def test_python_rest_ncs() -> None:
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_rest_scs_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_python_config.yaml"

    fuzzer = TelePhuzz()
    fuzzer.start_fuzzing_session()


def test_python_http_patch_spring() -> None:
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_http_patch_spring_config.yaml"
    Config.CLIENT_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "client_python_config.yaml"

    fuzzer = TelePhuzz()
    fuzzer.start_fuzzing_session()
