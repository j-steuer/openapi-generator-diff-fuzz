"""Worker for running Python scripts in client docker container."""

import os
import runpy
import time
import traceback

SCRIPT_PATH = "/tmp/invocation.py"
TRIGGER_PATH = "/tmp/run.trigger"
POLL_INTERVAL = 0.05  # seconds


def run_script():
    print(f"Executing {SCRIPT_PATH}")

    try:
        runpy.run_path(SCRIPT_PATH, run_name="__main__")
    except Exception:
        print("Script failed:")
        traceback.print_exc()
    else:
        print("Script completed successfully")


def main():
    print("Worker started.")

    while True:
        if os.path.exists(TRIGGER_PATH):
            # Consume the trigger
            os.remove(TRIGGER_PATH)

            if os.path.exists(SCRIPT_PATH):
                run_script()
            else:
                print(f"{SCRIPT_PATH} does not exist.")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
