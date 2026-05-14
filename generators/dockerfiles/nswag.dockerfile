FROM mcr.microsoft.com/dotnet/sdk:10.0

# Install NSwag CLI
RUN dotnet tool install --global NSwag.ConsoleCore --version 14.7.1

# Add .NET global tools to PATH
ENV PATH="${PATH}:/root/.dotnet/tools"

# Optional working directory
WORKDIR /app

# Default command
ENTRYPOINT ["nswag"]