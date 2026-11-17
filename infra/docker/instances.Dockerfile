# Build context is backend/. instances on .NET (#42, #44), for the dev stack: `dotnet watch`
# against the bind-mounted source, so edits rebuild and restart it.
FROM mcr.microsoft.com/dotnet/sdk:10.0

ENV DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_NOLOGO=1 \
    DOTNET_USE_POLLING_FILE_WATCHER=1 \
    ASPNETCORE_URLS=http://+:8000

WORKDIR /app/instances

# Restore first, for layer caching.
COPY instances/global.json instances/Directory.Build.props instances/Directory.Packages.props ./
COPY instances/src/Instances.Api/Instances.Api.csproj src/Instances.Api/
RUN dotnet restore src/Instances.Api

COPY instances/ ./

EXPOSE 8000

# Migrate (adopting a database Django built), then serve and rebuild on change.
CMD ["sh", "-c", "dotnet run --project src/Instances.Api -- migrate && exec dotnet watch --project src/Instances.Api run --no-launch-profile --non-interactive"]
