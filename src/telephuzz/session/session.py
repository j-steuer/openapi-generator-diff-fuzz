"""File for managing and creating sessions."""

import socket
from contextlib import ExitStack
from pathlib import Path

import docker
from docker.errors import NotFound

from telephuzz.config import get_config
from telephuzz.constants import DOCKER_NETWORK_NAME
from telephuzz.docker_helpers import (
    compose_down,
    compose_up,
    set_port_env,
    write_to_container,
    write_to_host,
)
from telephuzz.http_message import Request, Response
from telephuzz.request_result import RequestResult
from telephuzz.session.api import APIContainer, APIWithDatabaseContainer
from telephuzz.session.client_library import ClientLibraryContainer, LibraryId
from telephuzz.session.mitm_proxy.mitm_proxy import MITMProxyContainer


class Session:
    """A single client-api session."""

    def __init__(self, api: APIContainer, client: ClientLibraryContainer):
        """Set up session with client and api."""
        self.api = api
        self.client = client

    def send(self, request: Request, api_path: str) -> RequestResult:
        """Send a request to the API through the client library."""
        if not isinstance(self.api, APIWithDatabaseContainer):
            response = self.client.send(request, api_path)
            assert isinstance(response, Response)
            return RequestResult(self.client.id, request, response, None, None)
        else:
            out_before = Path("/tmp/before")
            out_after = Path("/out/after")
            self.api.get_state(out_before)
            response = self.client.send(request, api_path)
            assert isinstance(response, Response)
            self.api.get_state(out_after)

            # TODO path within project?
            out_before_host = out_before / self.client.id
            out_after_host = out_after / self.client.id
            assert self.api.db_container is not None
            write_to_host(self.api.db_container, str(out_before), out_before_host)
            write_to_host(self.api.db_container, str(out_after), out_after_host)

            return RequestResult(
                self.client.id, request, response, out_before_host, out_after_host
            )

    def change_api_proxy(self, container: APIWithDatabaseContainer) -> None:
        """Replace the API proxy with another container."""
        if not (
            isinstance(container, APIWithDatabaseContainer)
            and isinstance(self.api, APIWithDatabaseContainer)
        ):
            raise ValueError("Both target and source APIs need a database.")

        path = Path("/export")
        container.export_db_state(path)
        assert self.api.db_container is not None
        assert container.db_container is not None
        write_to_container(self.api.db_container, container.db_container, path)
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

        client_libraries = [
            ClientLibraryContainer.from_id(id_) for id_ in config.targets
        ]

        if len(client_libraries) <= 1:
            raise TypeError("Must have at least two client libraries under test.")
        self.client_libraries = client_libraries
        self.api_port_name = config.api_port_name
        self.port_names = config.port_names

        self.sessions: dict[LibraryId, Session] = dict()

        self.db_name = db_name
        self.database_type = config.database_type

        self.stack = ExitStack()

    def _get_project_name(self, id: LibraryId) -> str:
        """Get the docker compose project id for a library."""
        return f"api_{id}"

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
        env = set_port_env(port_map)
        return env

    def __enter__(self) -> None:
        """Initialize session manager and docker network, clients, apis and proxy."""
        # create docker network
        client = docker.from_env()

        try:
            # reset network if it already exists
            network = client.networks.get(DOCKER_NETWORK_NAME)
            network.remove()
        except NotFound:
            pass

        client.networks.create(name=DOCKER_NETWORK_NAME)

        # start up mitmproxy
        self.mitmproxy = self.stack.enter_context(MITMProxyContainer())

        # start up client libraries
        for client_library in self.client_libraries:
            client_container: ClientLibraryContainer = self.stack.enter_context(
                client_library()
            )

            project_name = self._get_project_name(client_container.id)

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

            session = Session(api=api_container, client=client_container)

            self.sessions[client_container.id] = session

    def __exit__(self) -> None:
        """Exit and close session-related containers."""
        for id in self.sessions.keys():
            compose_down(self.api_docker_compose_path, self._get_project_name(id))

        self.stack.close()

    def send(self, request: Request) -> set[RequestResult]:
        """Send a request through all libraries."""
        results: set[RequestResult] = set()
        for session in self.sessions.values():
            api_port = session.api.port
            proxy_request = self.mitmproxy.through_proxy(request, api_port)
            results.add(
                session.send(
                    proxy_request, f"http://localhost:{self.mitmproxy.listen_port}"
                )
            )

        return results
