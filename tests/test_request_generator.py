"""Tests for request generation."""

from pathlib import Path

from telephuzz.operation_ids import generate_operation_id
from telephuzz.request_generator import SchemathesisGenerator

OAS_PATH = Path(__file__).resolve().parent / "testfiles" / "openapi.json"


def test_simple_schemathesis_generator(api):
    """Run SchemathesisGenerator for 3 seconds and perform basic request checks."""
    with SchemathesisGenerator(
        OAS_PATH, "http://localhost:8000", max_time_seconds=3
    ) as generator:
        generator.generate()

        assert len(generator.pregenerated_requests) >= 1, "No requests were generated."

        # run basic Request structure assertions
        for idx, request in enumerate(generator.pregenerated_requests):
            print(f"Request {idx}: {repr(request)}")

            # method should be GET or POST
            assert request.method.value in ["GET", "POST"], request.method.value

            # path should be /greet or /user
            assert "/greet" in request.path or "/user" in request.path

            # query parameters should match in path and query_parameters
            if "?" in request.path:
                assert request.query_parameters, (
                    f"Query parameters in path {request.path}, "
                    "but empty query parameters"
                )


def test_method_name_schemathesis_generator(api):
    """Test always being able to infer a method name from Schemathesis generator."""
    with SchemathesisGenerator(
        OAS_PATH, "http://localhost:8000", max_time_seconds=3
    ) as generator:
        generator.generate()

        assert len(generator.pregenerated_requests) >= 1, "No requests were generated."

        method_names = [
            generate_operation_id("GET", "/greet"),
            generate_operation_id("GET", "/user"),
            generate_operation_id("POST", "/user"),
        ]
        for request in generator.pregenerated_requests:
            operation_id = generate_operation_id(request.method.value, request.path)
            assert operation_id in method_names
