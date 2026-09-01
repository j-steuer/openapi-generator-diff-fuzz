import pytest
from conftest import TEST_CONFIG_3_0_BASE_PATH
from requests.models import CaseInsensitiveDict

from telephuzz.config import Config
from telephuzz.http_message import HTTPMethod, Request
from telephuzz.session.session import SessionManager


@pytest.mark.xfail(
    reason=(
        "Fails due to OpenAPI Generator Python using urllib3, "
        "which strips trailing dots from the URL"
    )
)
def test_dot_path_variable():
    """Test correct translation of dot path variable."""
    Config.API_CONFIG_PATH = (
        TEST_CONFIG_3_0_BASE_PATH / "api_swagger_petstore_config.yaml"
    )

    request = Request(
        headers=CaseInsensitiveDict(),
        body=b"",
        method=HTTPMethod.GET,
        path="/user/.",
        query_parameters={},
    )

    with SessionManager("openapi-generator:python") as session_manager:
        session_manager.send(request)
        results = session_manager.send(request)

        result = next(iter(results))

        assert result.request
        assert result.request.path == request.path
