"""Helper methods related to reading and parsing config."""

import yaml  # type: ignore

from telephuzz.constants import BASE_PATH


class Config:
    """Class for reading the config."""

    API_CONFIG_PATH = BASE_PATH / "api_config.yaml"
    CLIENT_CONFIG_PATH = BASE_PATH / "client_config.yaml"

    def __init__(self):
        """Parse config attributes."""
        api_config, client_config = self._get_config()

        assert isinstance(api_config, dict)
        self.api_container_name = api_config["container-name"]
        self.compose_path = api_config["compose-path"]
        self.spec_path = (
            api_config["spec-path"]
            if "spec-path" in api_config
            else str(BASE_PATH / "spec" / "openapi.json")
        )
        self.database_type = api_config.get("database-type")
        self.api_port_name = api_config["api-port-name"]
        self.port_names = set(api_config["port-names"])
        self.port_names.add(self.api_port_name)
        self.nondeterministic_fields = api_config.get("nondeterministic-fields", {})
        for method, paths in self.nondeterministic_fields.items():
            for path, fields in paths.items():
                self.nondeterministic_fields[method][path] = set(fields)

        self.targets = dict()
        for target in client_config["targets"]:
            self.targets[target["id"]] = target["lib_name"]

        fuzzing_config = client_config["fuzzing"]
        assert isinstance(fuzzing_config, dict)
        self.log_path = fuzzing_config["log-path"]
        self.timeout = fuzzing_config["timeout"]

    def _get_config(self) -> tuple[dict, dict]:
        """Obtain the config as a dict."""
        with open(self.API_CONFIG_PATH) as api_stream:
            with open(self.CLIENT_CONFIG_PATH) as client_stream:
                try:
                    return yaml.safe_load(api_stream), yaml.safe_load(client_stream)
                except yaml.YAMLError as e:
                    raise ValueError("Invalid config.") from e


# ---- lazy singleton state ----
_config: Config | None = None


def get_config() -> Config:
    """Parse static config only once."""
    global _config
    if _config is None:
        _config = Config()
    return _config
