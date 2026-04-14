"""File for pytest fixtures."""

import pytest

from telephuzz.http_message import HTTPMethod, Request


@pytest.fixture
def basic_request():
    """Fixture for dummy request if content is not relevant."""
    return Request(
        headers={"Test": ["test"]},
        body=None,
        content_type=None,
        method=HTTPMethod.GET,
        target="dummytarget.org/test",
        parameters={},
    )
