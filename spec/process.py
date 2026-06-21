from telephuzz.constants import BASE_PATH
from telephuzz.fuzzer import TelePhuzz

if __name__ == "__main__":
    telephuzz = TelePhuzz.__new__(TelePhuzz)
    path = BASE_PATH / "spec" / "openapi.json"
    telephuzz._preprocess_oas(path, path)
