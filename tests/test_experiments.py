import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import BASE_PATH, TEST_CONFIG_BASE_PATH

from telephuzz.config import Config
from telephuzz.fuzzer import TelePhuzz

JACOCO_PATH = BASE_PATH / "wfd" / "jacoco"
COVERAGE_EXEC_PATH = JACOCO_PATH / "coverage.exec"
JACOCO_EXEC_PATH = JACOCO_PATH / "jacoco.exec"

COVERAGE_REPORT_PATH = BASE_PATH / "reports" / "coverage"


@pytest.fixture(autouse=True)
def reset_docker(request):
    """Make sure containers and networks are reset between experiments."""
    subprocess.run(["./reset_docker.sh"], check=True)

    yield

    shutil.copy("./reports/diffs/experiment", f"./reports/diffs/{request.node.name}")


@pytest.fixture(autouse=False)
def move_jacoco_coverage(request):
    """Save jacoco coverage files between tests."""

    yield

    out_path = Path(COVERAGE_REPORT_PATH / request.node.name)
    out_path.mkdir(parents=True, exist_ok=True)
    shutil.copy(COVERAGE_EXEC_PATH, out_path / "coverage.exec")
    shutil.copy(JACOCO_EXEC_PATH, out_path / "jacoco.exec")


def test_python_petshop_openapi_generator() -> None:
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_petshop_config.yaml"
    Config.CLIENT_CONFIG_PATH = (
        TEST_CONFIG_BASE_PATH / "client_openapi_generator_python.yaml"
    )

    fuzzer = TelePhuzz()
    fuzzer.start_fuzzing_session()


def test_python_springbatch_openapi_generator() -> None:
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_springbatch_config.yaml"
    Config.CLIENT_CONFIG_PATH = (
        TEST_CONFIG_BASE_PATH / "client_openapi_generator_python.yaml"
    )

    fuzzer = TelePhuzz()
    fuzzer.start_fuzzing_session()


def test_python_patchspring_openapi_generator() -> None:
    Config.API_CONFIG_PATH = TEST_CONFIG_BASE_PATH / "api_http_patch_spring_config.yaml"
    Config.CLIENT_CONFIG_PATH = (
        TEST_CONFIG_BASE_PATH / "client_openapi_generator_python.yaml"
    )

    fuzzer = TelePhuzz()
    fuzzer.start_fuzzing_session()
