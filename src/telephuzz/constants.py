"""File for constants used across various files."""

from pathlib import Path

MITMPROXY = "mitmproxy"

BASE_PATH = Path(__file__).parent.parent.parent
CLIENT_PATH = BASE_PATH / "clients"
