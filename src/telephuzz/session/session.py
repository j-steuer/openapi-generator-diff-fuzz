"""File for managing and creating sessions."""

import logging
import tempfile
from contextlib import ExitStack
from pathlib import Path
from time import sleep
from typing import cast

import docker
from docker.models.networks import Network

from telephuzz.config import get_config
from telephuzz.http_message import Request
from telephuzz.invocation_data import InvocationData
from telephuzz.request_result import RequestResult
from telephuzz.session.client_library import ClientLibraryContainer, LibraryId
from telephuzz.session.mitm_proxy.mitm_proxy import MITMProxyContainer

logger = logging.getLogger(__name__)

CLIENT_ALIAS = "client"
MITMPROXY_ALIAS = "mitmproxy"


class Session:
    """A single client-api session."""

    def __init__(self, id: int, client: ClientLibraryContainer):
        """Set up session with client and api."""
        self.id = id
        self.client = client
        self.first: bool = True

    def send(
        self,
        request: Request,
        api_path: str,
        response_output: Path,
        invocation: InvocationData | None = None,
    ) -> RequestResult | None:
        """Send a request to the API through the client library.

        Returns None if no response could be retrieved in time.
        """
        logger.debug(f"Sending request through clients: {request}")

        def _get_request() -> Request | None:
            response_dir = response_output / "mitmproxy"
            response_path = None
            for _ in range(30):
                try:
                    response_path = next(response_dir.iterdir())
                    break
                except (FileNotFoundError, StopIteration):
                    sleep(0.1)
            if response_path is None:
                return None

            request = Request.from_json(response_path)

            response_path.unlink()
            return request

        # process request to invocation data if not done already
        if invocation is None:
            invocation = InvocationData(request)

        # send message
        self.client.send(invocation, api_path)
        library_request = _get_request()
        if library_request is None and self.first:
            for i in range(5):
                sleep(1)
                self.client.send(invocation, api_path)
                library_request = _get_request()

                if library_request is not None or i == 5:
                    self.first = False
                    break
        elif self.first:
            self.first = False

        if not (isinstance(library_request, Request) or library_request is None):
            raise ValueError("Response was not parsed into response object.")
        result = RequestResult(self.client.id, cast(Request, library_request))

        return result


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
        for target in self.targets:
            library_id = target["id"]
            logger.info(f"Starting up {library_id}")
            lib_class: type = ClientLibraryContainer.from_id(library_id)
            client_container: ClientLibraryContainer = self.stack.enter_context(
                lib_class()
            )

            network_name = f"network-{library_id}"

            session = Session(id=len(self.networks), client=client_container)

            # add client container and mitmproxy to same network
            network = client.networks.create(network_name)
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
        self.stack.close()

        for network in self.networks:
            network.remove()

    def send(self, request: Request) -> set[RequestResult]:
        """Send a request through all libraries."""
        results: set[RequestResult] = set()

        for session in self.sessions.values():
            api_url = f"http://{MITMPROXY_ALIAS}:{self.mitmproxy.listen_port}"
            # process into invocation data to do it once per request
            try:
                invocation = InvocationData(request)
            except Exception:
                logger.error(
                    "Error occured while transforming original "
                    "request to invocation: {e}"
                )

            try:
                result = session.send(
                    request, api_url, Path(self.result_dir), invocation=invocation
                )
                assert result
                results.add(result)
            except Exception as e:
                logger.error(
                    f"Fuzzer error occured while sending request {repr(request)}: {e}"
                )

        return results
