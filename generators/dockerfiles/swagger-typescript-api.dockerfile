FROM node:20-alpine

# Install the CLI globally
RUN npm install -g swagger-typescript-api

# Create working directory
WORKDIR /app

RUN npm i -D tsx

# Default shell
ENTRYPOINT ["swagger-typescript-api"]