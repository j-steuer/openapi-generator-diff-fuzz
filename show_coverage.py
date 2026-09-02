import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def run_jacoco(jacoco_cli: Path, args: list[str]) -> None:
    cmd = ["java", "-jar", str(jacoco_cli), *args]

    print("$", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)


def extract_jar(jar: Path, destination: Path) -> None:
    print(f"Extracting classes from {jar}")
    with zipfile.ZipFile(jar, "r") as zf:
        zf.extractall(destination)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate an HTML JaCoCo coverage report for a WFD API."
    )

    parser.add_argument(
        "exec_file",
        type=Path,
        help="Path to jacoco.exec",
    )

    parser.add_argument(
        "jar",
        type=Path,
        help="API JAR from the dist directory",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("jacoco-report"),
        help="Output directory (default: jacoco-report)",
    )

    parser.add_argument(
        "--jacoco-cli",
        type=Path,
        default=Path("wfd/jacoco/jacococli.jar"),
        help="Path to jacococli.jar",
    )

    parser.add_argument(
        "--name",
        default=None,
        help="Name of the coverage report",
    )

    parser.add_argument(
        "--xml",
        action="store_true",
        help="Also generate coverage.xml",
    )

    parser.add_argument(
        "--csv",
        action="store_true",
        help="Also generate coverage.csv",
    )

    parser.add_argument(
        "--execinfo",
        action="store_true",
        help="Only display information contained in jacoco.exec",
    )

    args = parser.parse_args()

    # Validate inputs.
    if not args.exec_file.is_file():
        print(f"ERROR: {args.exec_file} does not exist", file=sys.stderr)
        return 1

    if not args.jar.is_file():
        print(f"ERROR: {args.jar} does not exist", file=sys.stderr)
        return 1

    if not args.jacoco_cli.is_file():
        print(
            f"ERROR: JaCoCo CLI not found: {args.jacoco_cli}",
            file=sys.stderr,
        )
        return 1

    # Useful when debugging collection.
    if args.execinfo:
        run_jacoco(
            args.jacoco_cli,
            [
                "execinfo",
                str(args.exec_file),
            ],
        )
        return 0

    args.output.mkdir(parents=True, exist_ok=True)

    # JaCoCo report expects class files. Extract the application JAR
    # into a temporary directory.
    with tempfile.TemporaryDirectory(prefix="jacoco-classes-") as tmp:
        extracted_dir = Path(tmp)

        extract_jar(args.jar, extracted_dir)

        # Spring Boot executable JARs put application classes here:
        boot_classes = extracted_dir / "BOOT-INF" / "classes"

        if boot_classes.is_dir():
            classes_dir = boot_classes
        else:
            # Fall back to a normal JAR layout.
            classes_dir = extracted_dir

        report_name = args.name or args.jar.stem

        cmd = [
            "report",
            str(args.exec_file),
            "--classfiles",
            str(classes_dir),
            "--html",
            str(args.output),
            "--name",
            report_name,
        ]

        if args.xml:
            cmd.extend(
                [
                    "--xml",
                    str(args.output / "coverage.xml"),
                ]
            )

        if args.csv:
            cmd.extend(
                [
                    "--csv",
                    str(args.output / "coverage.csv"),
                ]
            )

        try:
            run_jacoco(args.jacoco_cli, cmd)
        except subprocess.CalledProcessError as e:
            print(
                f"ERROR: JaCoCo exited with status {e.returncode}",
                file=sys.stderr,
            )
            return e.returncode

    index = args.output / "index.html"

    print()
    print("Coverage report generated successfully.")
    print(f"Report: {index}")
    print()
    print("Open with:")
    print(f"  file://{index.resolve()}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
