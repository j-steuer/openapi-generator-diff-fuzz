"""Helper methods for docker."""

import tempfile
from pathlib import Path

from docker.models.containers import Container


def write_to_container(
    source_container: Container, target_container: Container, path: Path
) -> None:
    """Write file from one container to another."""
    path_str = str(path)
    stream, _ = source_container.get_archive(path_str)

    with tempfile.NamedTemporaryFile(mode="wb+", delete=True) as temp_file:
        for chunk in stream:
            temp_file.write(chunk)
        temp_file.seek(0)

        target_container.put_archive("/", temp_file.read())
