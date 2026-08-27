import subprocess

import pytest
from conftest import BASE_PATH, TEST_CONFIG_BASE_PATH

from telephuzz.config import Config
from telephuzz.fuzzer import TelePhuzz

JACOCO_PATH = BASE_PATH / "wfd" / "jacoco"
COVERAGE_EXEC_PATH = JACOCO_PATH / "coverage.exec"
JACOCO_EXEC_PATH = JACOCO_PATH / "jacoco.exec"

REPORT_PATH = BASE_PATH / "reports"


@pytest.fixture(autouse=True)
def reset_docker():
    """Make sure containers and networks are reset between experiments."""
    subprocess.run(["./reset_docker.sh"], check=True)

    yield


def test_python_petshop_openapi_generator(request) -> None:
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"

    fuzzer = TelePhuzz("openapi-generator:python", REPORT_PATH / request.node.name)
    fuzzer.start_fuzzing_session()


def test_python_springbatch_openapi_generator(request) -> None:
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"

    fuzzer = TelePhuzz("openapi-generator:python", REPORT_PATH / request.node.name)
    fuzzer.start_fuzzing_session()


def test_python_patchspring_openapi_generator(request) -> None:
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_http_patch_spring_config.yaml"

    fuzzer = TelePhuzz("openapi-generator:python", REPORT_PATH / request.node.name)
    fuzzer.start_fuzzing_session()
