"""Tests for request generation."""

import os
from pathlib import Path
from time import sleep

from telephuzz.operation_ids import generate_operation_id
from telephuzz.request_generator import SchemathesisGenerator

OAS_PATH = Path(__file__).resolve().parent / "testfiles" / "openapi.json"


def test_simple_schemathesis_generator(api):
    """Run SchemathesisGenerator for 3 seconds and perform basic request checks."""
    with SchemathesisGenerator(
        OAS_PATH, "http://localhost:8000", max_time_seconds=3
    ) as generator:
        sleep(0.5)
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
        sleep(0.5)
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


def test_unique_requests(api):
    """Assert requests are not loaded twice."""
    with SchemathesisGenerator(
        OAS_PATH, "http://localhost:8000", max_time_seconds=5
    ) as generator:
        sleep(0.5)
        generator.generate()
        requests = set()
        requests.update(generator.pregenerated_requests)
        assert 0 < len(requests)
        assert len(requests) == len(generator.pregenerated_requests)

        generator.pregenerated_requests = []
        sleep(0.5)
        generator.generate()
        assert 0 < len(generator.pregenerated_requests)
        assert not any(
            request in requests for request in generator.pregenerated_requests
        )


def test_stop_and_resume(api):
    """Test stopping and resuming the generator."""
    with SchemathesisGenerator(
        OAS_PATH, "http://localhost:8000", max_time_seconds=5
    ) as generator:
        generator.pause()
        assert not generator.running

        # no new requests should be generated
        sleep(0.1)
        num_requests = len(os.listdir(generator.tmpdir))
        sleep(1)
        assert num_requests == len(os.listdir(generator.tmpdir))

        # resuming should generate new requests
        generator.resume()
        sleep(1)
        assert num_requests < len(os.listdir(generator.tmpdir))

        assert generator.running


def test_run(api):
    """Test that fuzzer is running for defined time interval."""
    with SchemathesisGenerator(
        OAS_PATH, "http://localhost:8000", max_time_seconds=5, batch_interval=1
    ) as generator:
        assert generator.running
        sleep(1)
        assert not generator.running

        # clear requests
        for file in Path(generator.tmpdir).iterdir():
            os.remove(file)

        # loop should start again when requesting files
        assert generator.generate()
        assert generator.running
        sleep(1)
        assert 0 < len(os.listdir(generator.tmpdir))
