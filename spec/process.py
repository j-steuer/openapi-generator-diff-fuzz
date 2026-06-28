from telephuzz.constants import BASE_PATH
from telephuzz.openapi_helpers import preprocess_oas

if __name__ == "__main__":
    path = BASE_PATH / "spec" / "openapi.json"
    preprocess_oas(path, path)
