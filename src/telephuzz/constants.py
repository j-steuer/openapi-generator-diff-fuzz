"""File for constants used across various files."""

from pathlib import Path

DOCKER_NETWORK_NAME = "telephuzz_network"
MITMPROXY = "mitmproxy"

BASE_PATH = Path(__file__).parent.parent.parent
CLIENT_PATH = BASE_PATH / "clients"
