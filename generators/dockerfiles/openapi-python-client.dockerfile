FROM python:3.12-slim

# Install openapi-python-client
RUN pip install --no-cache-dir openapi-python-client

# Create working directory
WORKDIR /work

# Default entrypoint
ENTRYPOINT ["openapi-python-client"]