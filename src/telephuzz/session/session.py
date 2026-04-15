"""File for managing and creating sessions."""

import docker
from docker.errors import NotFound
from docker.models.containers import Container

from telephuzz.constants import DOCKER_NETWORK_NAME
from telephuzz.http_message import Request
from telephuzz.request_result import RequestResult
from telephuzz.session.api import APIContainer
from telephuzz.session.client_library import ClientLibraryContainer
from telephuzz.session.mitm_proxy.mitm_proxy import MITMProxyContainer


class Session:
    """A single client-api session."""

    def __init__(self, api: APIContainer, client: ClientLibraryContainer):
        """Set up session with client and api."""
        self.api = api
        self.client = client

    def send(self, request: Request) -> RequestResult:
        """Send a request to the API through the client library."""
        raise NotImplementedError  # TODO

    def change_api_proxy(self, container: Container) -> None:
        """Replace the API proxy with another container."""
        raise NotImplementedError  # TODO


class SessionManager:
    """The class responsible for managing the client-api sessions."""

    def __init__(self) -> None:
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

        # start up MiTMProxy
        self.mitm_proxy = MITMProxyContainer()

        # start up client libraries and corresponding APIs
        # TODO
