"""Worker for running Python scripts in client docker container."""

import logging
import os
import runpy
import sys
import time
import traceback

SCRIPT_PATH = "/tmp/invocation.py"
TRIGGER_PATH = "/tmp/run.trigger"
POLL_INTERVAL = 0.05  # seconds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def run_script():
    logger.info(f"Executing {SCRIPT_PATH}")

    try:
        runpy.run_path(SCRIPT_PATH, run_name="__main__")
    except Exception:
        logger.error("Script failed:")
        traceback.print_exc()
    else:
        logger.info("Script completed successfully")


def main():
    logger.info("Worker started.")

    while True:
        if os.path.exists(TRIGGER_PATH):
            # Consume the trigger
            os.remove(TRIGGER_PATH)

            if os.path.exists(SCRIPT_PATH):
                run_script()
            else:
                logger.error(f"{SCRIPT_PATH} does not exist.")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
