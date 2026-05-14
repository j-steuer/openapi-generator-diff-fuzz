FROM node:20-alpine

# Install Orval CLI globally
RUN npm install -g orval

WORKDIR /app

ENTRYPOINT ["orval"]