import subprocess
from pathlib import Path

import pytest
from conftest import BASE_PATH, TEST_CONFIG_BASE_PATH

from telephuzz.config import Config
from telephuzz.fuzzer import TelePhuzz

JACOCO_PATH = BASE_PATH / "wfd" / "jacoco"
COVERAGE_EXEC_PATH = JACOCO_PATH / "coverage.exec"
JACOCO_EXEC_PATH = JACOCO_PATH / "jacoco.exec"

REPORT_PATH = BASE_PATH / "reports"

CONFIGS = []
for filepath in Path(TEST_CONFIG_BASE_PATH).glob("**/*"):
    CONFIGS.append(filepath.absolute())


@pytest.fixture(autouse=True)
def reset_docker():
    """Make sure containers and networks are reset between experiments."""
    subprocess.run(["./reset_docker.sh"], check=True)

    yield


@pytest.mark.parametrize("config", CONFIGS)
def test_openapi_generator_python(config: Path) -> None:
    Config.API_CONFIG_PATH = config

    report_suffix = config.name[: config.name.find(".yaml")]
    fuzzer = TelePhuzz(
        "openapi-generator:python",
        REPORT_PATH / f"openapi-generator-python_{report_suffix}",
    )
    fuzzer.start_fuzzing_session()
