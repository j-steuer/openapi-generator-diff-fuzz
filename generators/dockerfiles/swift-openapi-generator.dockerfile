FROM swift:6.3.1

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

RUN git clone https://github.com/apple/swift-openapi-generator.git \
    && cd swift-openapi-generator \
    && swift build -c release

RUN ln -s /opt/swift-openapi-generator/.build/release/swift-openapi-generator \
    /usr/local/bin/swift-openapi-generator

ENTRYPOINT ["swift-openapi-generator"]