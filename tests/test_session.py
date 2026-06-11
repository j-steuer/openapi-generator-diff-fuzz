"""Tests for Session Manager and Session objects."""

from unittest.mock import Mock
from uuid import uuid4

from telephuzz.http_message import Request
from telephuzz.session.session import Session, SessionManager


class TestSession:
    """Unit tests for Session."""

    def test_send_no_db(
        self, basic_request: Request, mock_client: Mock, mock_api_no_db: Mock
    ):
        """Test sending with no db."""
        session = Session(api=mock_api_no_db, client=mock_client)
        body = "TESTBODY"
        basic_request.body = body
        api_path = "http://localhost:8000"
        result = session.send(basic_request, api_path=api_path)
        assert result.request == basic_request
        assert result.response.body == mock_client.mock_body
        mock_client.send.assert_called_once_with(basic_request, api_path)


def test_allocate_ports():
    """Test allocating ports."""
    manager = SessionManager.__new__(SessionManager)
    ports = {f"{uuid4()}_PORT" for _ in range(100)}
    manager.port_names = ports
    env = manager._get_compose_env()

    # check that a port has been assigned to each name
    assert all(port in env for port in ports)

    # check that all ports are unique
    port_numbers = [env[port] for port in ports]
    assert len(port_numbers) == len(set(port_numbers))
