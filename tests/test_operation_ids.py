"""File for testing operation id related methods."""

from telephuzz.operation_ids import Case, generate_operation_id, transform_case


def test_operation_id_no_collision() -> None:
    """Test that there is no collision with parameter and literal path names."""
    method = "GET"
    base_path = "/test"
    assert generate_operation_id(method, f"{base_path}/id") != generate_operation_id(
        method, f"{base_path}/{{id}}"
    )


def test_operation_id_deterministic() -> None:
    """Obtaining the operation id should be deterministic."""
    method = "GET"
    path = "/test/{id}"

    assert generate_operation_id(method, path) == generate_operation_id(method, path)


def test_transform_case_snake() -> None:
    """Test transforming operation id to snake case."""
    operation_id = generate_operation_id("GET", "/test/{id}")
    assert "get_test_id" in transform_case(operation_id, Case("snake"))


def test_transform_case_camel() -> None:
    """Test transforming operation id to camel case."""
    operation_id = generate_operation_id("GET", "/test/{id}")
    assert "getTestId" in transform_case(operation_id, Case("camel"))


def test_transform_case_pascal() -> None:
    """Test transforming operation id to camel pascal."""
    operation_id = generate_operation_id("GET", "/test/{id}")
    assert "GetTestId" in transform_case(operation_id, Case("pascal"))


def test_operation_ids_ignore_query() -> None:
    """Query parameters should be ignored when generating the operation id."""
    operation_id_no_query = generate_operation_id("GET", "/test")
    operation_id_with_qury = generate_operation_id("GET", "/test?example=0")
    assert operation_id_no_query == operation_id_with_qury


def test_operation_ids_ignore_mitmproxy_target_prefix() -> None:
    """Mitmproxy target prefix should be ignored when generating the operation id."""
    operation_id_no_prefix = generate_operation_id("GET", "/test")
    operation_id_with_prefix = generate_operation_id("GET", "/api1:8000/test")
    assert operation_id_no_prefix == operation_id_with_prefix


def test_default_path() -> None:
    """Default path should return a valid id."""
    operation_id = generate_operation_id("GET", "/")

    # assert case can be transformed
    transform_case(operation_id, Case.SNAKE)
    transform_case(operation_id, Case.PASCAL)
    transform_case(operation_id, Case.CAMEL)
