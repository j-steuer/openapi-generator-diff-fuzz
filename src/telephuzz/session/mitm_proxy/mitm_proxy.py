"""File for the container with MiTMProxy."""

import pathlib

from telephuzz.constants import MITMPROXY
from telephuzz.docker_helpers import add_container_to_network, create_image
from telephuzz.http_message import Request
from telephuzz.session.client_library import LibraryId


class MITMProxyContainer:
    """Class for the MiTMProxy container."""

    def __init__(self) -> None:
        """Set up the proxy container and add it to the network."""
        # create image if it does not exist
        create_image(path=pathlib.Path(__file__).parent.resolve(), tag=MITMPROXY)

        # create container
        self.container = add_container_to_network(image=MITMPROXY, name=MITMPROXY)

    def through_proxy(self, request: Request, library_id: LibraryId) -> Request:
        """Make the request target the proxy and encode the target."""
        raise NotImplementedError
