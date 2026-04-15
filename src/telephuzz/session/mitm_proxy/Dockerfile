# Use official mitmproxy image as base
FROM mitmproxy/mitmproxy:latest

# Copy the dynamic routing script into the image
COPY dynamic_router.py /scripts/dynamic_router.py

# Set working directory
WORKDIR /scripts

# Default command
CMD ["mitmweb","--listen-port", "8080", "--web-port", "8081", "--web-host", "0.0.0.0", "-s", "/scripts/dynamic_router.py", "--set", "web_password=mitm"]