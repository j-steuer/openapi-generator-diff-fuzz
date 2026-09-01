## TelePhuzz
## A Fuzzing Framework for OpenAPI client generators

### Requirements

- Linux (likely will not work on other OS, the only confirmed OS is Fedora 43)
- Python 3.13+ and uv / pip
- Docker
- Java (if using WFD or wanting to measure coverage with Jacoco)

### Setup

1. Clone the repository (with submodules if you want to use WFD)
2. Install dependencies locally using uv/pip in edit mode, e.g. "uv pip install -e ."
3. (Optional) If you want to use WFD, follow instructions for setup here https://github.com/j-steuer/TelePhuzz_Dataset

### Usage
No CLI is currently implemented. The fuzzer has to be run using a script.

1. Ensure Docker is running
2. Set up your API config or choose from pre-defined ones
3. (Optional) Define your own request generator or use an existing one (see request_generator.py for default Schemathesis example)
4. (Optional) Set up your target API to be runnable (can improve results for some base fuzzers)
5. Set up a script to run Schemathesis (see tests/test_experiments.py for example)

If you simply wish to reproduce the experiment, ensure docker is running, WFD is set up and run pytest tests/test_experiments.py.
