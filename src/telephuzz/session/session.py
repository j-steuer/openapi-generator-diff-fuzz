"""File for managing and creating sessions."""

import logging
import re
import socket
import tempfile
from contextlib import ExitStack
from pathlib import Path

import docker
from docker.models.networks import Network

from telephuzz.config import get_config
from telephuzz.constants import CLIENT_PATH
from telephuzz.docker_helpers import (
    compose_down,
    compose_up,
    set_port_env,
    write_to_container,
    write_to_host,
)
from telephuzz.http_message import Request, Response
from telephuzz.openapi_helpers import get_api_url_path
from telephuzz.request_result import RequestResult
from telephuzz.session.api import APIContainer, APIWithDatabaseContainer
from telephuzz.session.client_library import ClientLibraryContainer, LibraryId
from telephuzz.session.mitm_proxy.mitm_proxy import MITMProxyContainer

logger = logging.getLogger(__name__)

API_ALIAS_BASE = "api"
CLIENT_ALIAS = "client"
MITMPROXY_ALIAS = "mitmproxy"


class Session:
    """A single client-api session."""

    def __init__(self, id: int, api: APIContainer, client: ClientLibraryContainer):
        """Set up session with client and api."""
        self.id = id
        self.api = api
        self.client = client

    def send(
        self, request: Request, api_path: str, response_output: Path
    ) -> RequestResult:
        """Send a request to the API through the client library."""

        def _get_response() -> Response:
            response_dir = response_output / f"api{self.id}"
            try:
                response_path = next(response_dir.iterdir())
            except StopIteration as e:
                raise RuntimeError("No response file found") from e

            response = Response.from_json(response_path)

            response_path.unlink()
            return response

        if not isinstance(self.api, APIWithDatabaseContainer):
            self.client.send(request, api_path)
            response = _get_response()
            result = RequestResult(self.client.id, request, response, None, None)
        else:
            out_before = Path("/tmp/before")
            out_after = Path("/out/after")
            self.api.get_state(out_before)
            self.client.send(request, api_path)
            response = _get_response()
            self.api.get_state(out_after)

            # TODO path within project?
            out_before_host = out_before / self.client.id
            out_after_host = out_after / self.client.id
            assert self.api.db_container is not None
            write_to_host(self.api.db_container, str(out_before), out_before_host)
            write_to_host(self.api.db_container, str(out_after), out_after_host)

            result = RequestResult(
                self.client.id, request, response, out_before_host, out_after_host
            )

        if result.response.status in [502, 503]:
            raise RuntimeError(
                "API server could not be reached, please check the configuration."
            )

        return result

    def change_api_proxy(self, container: APIWithDatabaseContainer) -> None:
        """Replace the API proxy with another container."""
        if not (
            isinstance(self.api, APIWithDatabaseContainer)
            and type(container) is type(self.api)
        ):
            raise ValueError(
                "Both target and source APIs need a database of the same type."
            )

        path = Path("/export")
        container.export_db_state(path)

        assert container.db_container is not None
        assert self.api.db_container is not None
        write_to_container(container.db_container, self.api.db_container, path)

        self.api.import_db_state(path)


class SessionManager:
    """The class responsible for managing the client-api sessions."""

    def __init__(
        self,
        db_name: str = "db",
    ):
        """Initialize the session manager."""
        config = get_config()
        self.api_docker_compose_path = config.compose_path
        self.api_name = config.api_container_name

        self.targets = config.targets

        if len(self.targets) <= 2:
            raise TypeError("Must have at least three client libraries under test.")
        self.api_path = get_api_url_path(config.spec)
        self.api_port_name = config.api_port_name
        self.port_names = config.port_names

        self.sessions: dict[LibraryId, Session] = dict()

        self.db_name = db_name
        self.database_type = config.database_type

        self.stack = ExitStack()
        self.networks: list[Network] = []

    def _get_project_name(self, id: LibraryId) -> str:
        """Get the docker compose project id for a library."""
        base = f"apicompose-{id}"
        project_name = base.replace(":", "-")
        return project_name

    def _get_compose_env(self) -> dict[str, str]:
        """Get env with free host ports for docker compose components.

        Does not account for race condition,
        but unlikely to be a problem in practice.
        """
        ports: set[int] = set()
        while len(ports) < len(self.port_names):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", 0))
                ports.add(s.getsockname()[1])
        port_map = {port_name: ports.pop() for port_name in self.port_names}
        logger.debug(f"Ports chosen: {port_map}")
        env = set_port_env(port_map)
        return env

    def __enter__(self) -> "SessionManager":
        """Initialize session manager and docker network, clients, apis and proxy."""
        client = docker.from_env()

        # start up mitmproxy
        logger.info("Setting up MITMProxy for request and response capturing.")
        self.result_dir = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.mitmproxy = self.stack.enter_context(
            MITMProxyContainer(response_output=self.result_dir)
        )

        # start up client
        logger.info("Starting up client libraries")
        for library_id, library_name in self.targets.items():
            logger.info(f"Starting up {library_id}")
            lib_class: type = ClientLibraryContainer.from_id(library_id)
            client_container: ClientLibraryContainer = self.stack.enter_context(
                lib_class(CLIENT_PATH / library_name)
            )

            project_name = self._get_project_name(client_container.id)
            network_name = f"network-{library_id}"

            env = self._get_compose_env()
            api_port = int(env[self.api_port_name])

            compose_up(self.api_docker_compose_path, env, project_name)

            api_containers = client.containers.list(
                all=True,
                filters={"label": f"com.docker.compose.project={project_name}"},
            )

            db_containers = [
                c
                for c in api_containers
                if c.name is not None and self.db_name in c.name
            ]
            if len(db_containers) == 1:
                db_container = db_containers[0]
            else:
                db_container = None

            if db_container is None:
                api_container = self.stack.enter_context(APIContainer(api_port))
            else:
                assert self.database_type is not None, (
                    "Database type must be provided when using APIs with a database."
                )
                api_container = self.stack.enter_context(
                    APIWithDatabaseContainer.from_id(self.database_type)(
                        db_container=db_container
                    )
                )

            session = Session(
                id=len(self.networks), api=api_container, client=client_container
            )

            # add api containers, client container and mitmproxy to same network
            network = client.networks.create(network_name)
            api_container = [
                c
                for c in api_containers
                if c.name is not None
                and re.search(rf"-{re.escape(self.api_name)}-\d+$", c.name)
            ]
            if len(api_container) != 1:
                raise ValueError(f"API container name {self.api_name} not found.")
            api_alias = f"{API_ALIAS_BASE}{len(self.networks)}"
            network.connect(api_container[0], aliases=[api_alias])
            assert client_container.container is not None
            network.connect(client_container.container, aliases=[CLIENT_ALIAS])
            assert self.mitmproxy.container is not None
            network.connect(self.mitmproxy.container, aliases=[MITMPROXY_ALIAS])
            self.networks.append(network)

            self.sessions[client_container.id] = session

        return self

    def __exit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        """Exit and close session-related containers."""
        for id in self.sessions.keys():
            compose_down(self.api_docker_compose_path, self._get_project_name(id))

        self.stack.close()

        for network in self.networks:
            network.remove()

    def send(self, request: Request) -> set[RequestResult]:
        """Send a request through all libraries."""
        results: set[RequestResult] = set()

        for session in self.sessions.values():
            api_url = f"http://{MITMPROXY_ALIAS}:{self.mitmproxy.listen_port}"
            api_url += f"/{API_ALIAS_BASE}{session.id}:8000{self.api_path}"
            results.add(
                session.send(
                    request,
                    api_url,
                    Path(self.result_dir),
                )
            )

        return results
