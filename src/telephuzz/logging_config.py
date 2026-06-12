import logging
import os


def setup_logging(level: str | None = None):
    """
    Simple global logging setup.
    Call once at app start.
    """

    # allow override via parameter or environment variable
    log_level = level or os.getenv("LOG_LEVEL", "CRITICAL")

    logging.basicConfig(
        level=log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
