"""Tests for request generation."""

from pathlib import Path

from telephuzz.request_generator import SchemathesisGenerator

OAS_PATH = Path(__file__).resolve().parent / "testfiles" / "openapi.json"


def test_simple_schemathesis_generator(api):
    """Run SchemathesisGenerator for 3 seconds and perform basic request checks."""
    generator = SchemathesisGenerator(
        OAS_PATH, "http://localhost:8000", max_time_seconds=3
    )

    assert len(generator.pregenerated_requests) >= 1, "No requests were generated."

    # run basic Request structure assertions
    for request in generator.pregenerated_requests:
        # query parameters should match in path and query_parameters
        if "?" in request.path:
            assert request.query_parameters, (
                f"Query parameters in path {request.path}, but empty query parameters"
            )
