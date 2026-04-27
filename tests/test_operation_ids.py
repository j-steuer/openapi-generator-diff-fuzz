"""File for testing operation id related methods."""  #

from telephuzz.operation_ids import generate_operation_id


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
