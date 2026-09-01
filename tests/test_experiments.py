import subprocess
from pathlib import Path

import pytest
from conftest import (
    BASE_PATH,
    TEST_CONFIG_2_0_BASE_PATH,
    TEST_CONFIG_3_0_BASE_PATH,
)

from telephuzz.config import Config
from telephuzz.fuzzer import TelePhuzz

JACOCO_PATH = BASE_PATH / "wfd" / "jacoco"
COVERAGE_EXEC_PATH = JACOCO_PATH / "coverage.exec"
JACOCO_EXEC_PATH = JACOCO_PATH / "jacoco.exec"

REPORT_PATH = BASE_PATH / "reports"

CONFIGS_2_0 = sorted(
    path.absolute()
    for path in TEST_CONFIG_2_0_BASE_PATH.glob("**/*.yaml")
    if path.is_file()
)
CONFIGS_3_0 = sorted(
    path.absolute()
    for path in TEST_CONFIG_3_0_BASE_PATH.glob("**/*.yaml")
    if path.is_file()
)


@pytest.fixture(autouse=True)
def reset_docker():
    """Make sure containers and networks are reset between experiments."""
    subprocess.run(["./reset_docker.sh"], check=True)

    yield


@pytest.mark.parametrize(
    "config",
    CONFIGS_2_0,
    ids=lambda config: config.stem,
)
def test_openapi_generator_python_2_0(config: Path) -> None:
    Config.API_CONFIG_PATH = config

    report_suffix = config.name[: config.name.find(".yaml")]
    fuzzer = TelePhuzz(
        "openapi-generator:python",
        REPORT_PATH / f"openapi-generator-python_{report_suffix}",
    )
    fuzzer.start_fuzzing_session()


@pytest.mark.parametrize(
    "config",
    CONFIGS_3_0,
    ids=lambda config: config.stem,
)
def test_openapi_generator_python_3_0(config: Path) -> None:
    Config.API_CONFIG_PATH = config

    report_suffix = config.name[: config.name.find(".yaml")]
    fuzzer = TelePhuzz(
        "openapi-generator:python",
        REPORT_PATH / f"openapi-generator-python_{report_suffix}",
    )
    fuzzer.start_fuzzing_session()


@pytest.mark.parametrize(
    "config",
    CONFIGS_3_0,
    ids=lambda config: config.stem,
)
def test_openapi_python_client(config: Path) -> None:
    Config.API_CONFIG_PATH = config

    report_suffix = config.name[: config.name.find(".yaml")]
    fuzzer = TelePhuzz(
        "openapi-python-client:python",
        REPORT_PATH / f"openapi-python-client_{report_suffix}",
        timeout=60,
    )
    fuzzer.start_fuzzing_session()
