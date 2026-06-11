"""Helper methods for docker."""

import os
import subprocess
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path

from docker.models.containers import Container


def set_port_env(port_map: dict[str, int]) -> dict[str, str]:
    """Obtain local env with ports mapped."""
    return {
        **os.environ,
        **{k: str(v) for k, v in port_map.items()},
    }


def compose_up(
    compose_path: Path, env: dict[str, str] | None = None, project: str = ""
):
    """Run docker compose up."""
    cmd = ["docker", "compose", "-f", str(compose_path)]
    if project:
        cmd += ["-p", project]
    cmd += ["up", "-d"]
    subprocess.run(
        cmd,
        env=env,
        check=True,
    )


def compose_down(compose_path: Path, project: str = "", graceful: bool = False) -> None:
    """Run docker compose down."""
    cmd = ["docker", "compose", "-f", str(compose_path)]
    if project:
        cmd += ["-p", project]
    cmd += ["down", "-v"]
    if not graceful:
        cmd += ["-t", "0"]
    subprocess.run(
        cmd,
        check=True,
    )


def write_to_host(
    container: Container,
    container_path: str,
    output_path: str | Path,
) -> None:
    """Copy a file from a Docker container to the host.

    Args:
        container: Docker container instance.
        container_path: Absolute path to the file inside the container.
        output_path: Destination path on the host.

    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    archive, _ = container.get_archive(container_path)

    tar_bytes = BytesIO()
    for chunk in archive:
        tar_bytes.write(chunk)

    tar_bytes.seek(0)

    with tarfile.open(fileobj=tar_bytes) as tar:
        members = [m for m in tar.getmembers() if m.isfile()]

        if len(members) != 1:
            raise ValueError(
                f"Expected exactly one file in archive, found {len(members)}"
            )

        member = members[0]
        extracted = tar.extractfile(member)

        if extracted is None:
            raise ValueError(f"Could not extract {container_path}")

        with output_path.open("wb") as f:
            f.write(extracted.read())


def write_to_container(
    source_container: Container, target_container: Container, path: Path
) -> None:
    """Write file from one container to another."""
    path_str = str(path)

    # check path exists in source container
    exit_code, _ = source_container.exec_run(f"test -e {path_str}")
    if exit_code != 0:
        raise ValueError("Path does not exist in source container.")

    stream, _ = source_container.get_archive(path_str)

    with tempfile.NamedTemporaryFile(mode="wb+", delete=True) as temp_file:
        for chunk in stream:
            temp_file.write(chunk)
        temp_file.seek(0)

        target_container.put_archive("/", temp_file.read())
