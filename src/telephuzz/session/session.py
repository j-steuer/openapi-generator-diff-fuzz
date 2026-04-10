from docker.models.containers import Container

from telephuzz.http_message import Request
from telephuzz.request_result import RequestResult
from telephuzz.session.api import APIContainer
from telephuzz.session.client_library import ClientLibraryContainer


class Session:
    def __init__(self, api: APIContainer, client: ClientLibraryContainer):
        self.api = api
        self.client = client

    def send(self, request: Request) -> RequestResult:
        raise NotImplementedError  # TODO

    def change_api_proxy(self, container: Container) -> None:
        raise NotImplementedError  # TODO
