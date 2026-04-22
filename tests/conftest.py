"""File for pytest fixtures."""

import pytest
from requests.structures import CaseInsensitiveDict

from telephuzz.http_message import HTTPMethod, Request


@pytest.fixture
def basic_request():
    """Fixture for dummy request if content is not relevant."""
    return Request(
        headers=CaseInsensitiveDict({"Test": ["test"]}),
        body=None,
        content_type=None,
        method=HTTPMethod.GET,
        path="dummytarget.org/test",
        path_parameters={},
        query_parameters={},
    )
