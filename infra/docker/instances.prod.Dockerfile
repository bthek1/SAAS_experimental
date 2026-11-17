# Build context is backend/. instances on .NET (#42, #44). From the repo root:
#   docker build -f infra/docker/instances.prod.Dockerfile backend
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src/instances
COPY instances_NET/global.json instances_NET/Directory.Build.props instances_NET/Directory.Packages.props ./
COPY instances_NET/src/Instances.Api/Instances.Api.csproj src/Instances.Api/
RUN --mount=type=cache,target=/root/.nuget/packages \
    dotnet restore src/Instances.Api
COPY instances_NET/src src
RUN --mount=type=cache,target=/root/.nuget/packages \
    dotnet publish src/Instances.Api -c Release -o /out --no-restore

# The ASP.NET runtime only. No Pango or fonts: PDFs are QuestPDF, which brings its own.
FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /out .
ENV ASPNETCORE_URLS=http://+:8000 \
    DOTNET_CLI_TELEMETRY_OPTOUT=1
USER app
EXPOSE 8000
# `dotnet Instances.Api.dll migrate` and `seed-loadtest` run in the same image.
CMD ["dotnet", "Instances.Api.dll"]
