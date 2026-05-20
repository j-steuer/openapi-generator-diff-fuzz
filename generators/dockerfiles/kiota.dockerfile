FROM mcr.microsoft.com/dotnet/sdk:8.0

# Install Kiota CLI as a global .NET tool
RUN dotnet tool install --global Microsoft.OpenApi.Kiota

# Add .NET global tools to PATH
ENV PATH="${PATH}:/root/.dotnet/tools"

# Verify installation
RUN kiota --version

# Default shell
WORKDIR /workspace

ENTRYPOINT ["kiota"]