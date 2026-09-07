FROM mcr.microsoft.com/dotnet/sdk:8.0

ENV DOTNET_ROOT=/usr/share/dotnet
ENV PATH="${PATH}:/opt/dotnet-tools"

RUN dotnet tool install \
    --tool-path /opt/dotnet-tools \
    --version 1.35.0 \
    Microsoft.OpenApi.Kiota

RUN kiota --version

WORKDIR /workspace

ENTRYPOINT ["kiota"]