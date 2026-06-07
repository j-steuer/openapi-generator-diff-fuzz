"""Helper methods related to reading and parsing config."""

import yaml  # type: ignore

from telephuzz.constants import CONFIG_PATH


def get_config() -> dict:
    """Obtain the config as a dict."""
    with open(CONFIG_PATH) as stream:
        try:
            return yaml.safe_load(stream)
        except yaml.YAMLError as e:
            raise ValueError("Invalid config.") from e
