"""Tests for Session Manager and Session objects."""

import tempfile
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from conftest import PrefillMethod

from telephuzz.http_message import Request
from telephuzz.session.api import APIH2DatabaseContainer
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

    def test_overwrite_db(self, prefilled_h2: PrefillMethod, mock_client: Mock):
        """Integration test for overwriting the API state."""
        insert_alice = """
        INSERT INTO users (id, name, email)
        VALUES
        (1, 'Alice', 'alice@example.com');
        """
        db_alice = prefilled_h2(8082, 9092, insert=insert_alice)

        insert_bob = """
        INSERT INTO users (id, name, email)
        VALUES
        (2, 'Bob', 'bob@example.com');
        """
        db_bob = prefilled_h2(8083, 9093, insert_bob)

        with (
            APIH2DatabaseContainer(
                port=8082, db_container=db_alice
            ) as db_container_alice,
            APIH2DatabaseContainer(port=8083, db_container=db_bob) as db_container_bob,
        ):
            session = Session(api=db_container_bob, client=mock_client)

            session.change_api_proxy(db_container_alice)

            with tempfile.NamedTemporaryFile(mode="w+") as f:
                db_container_bob.get_state(Path(f.name))
                f.seek(0)
                result = f.read()

            assert "Alice" in result
            assert "Bob" not in result


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
