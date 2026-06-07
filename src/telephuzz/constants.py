"""File for constants used across various files."""

from pathlib import Path

DOCKER_NETWORK_NAME = "telephuzz_network"
MITMPROXY = "mitmproxy"

BASE_PATH = Path(__file__).parent.parent.parent
CONFIG_PATH = BASE_PATH / "config.yaml"
