# Build context is backend/ — from the repo root run:
#   docker build -f infra/docker/catalog.prod.Dockerfile backend
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY common/pyproject.toml common/pyproject.toml
COPY catalog/pyproject.toml catalog/pyproject.toml
COPY instances/pyproject.toml instances/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev --package catalog
ADD . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package catalog

# Then, use a final image without uv
FROM python:3.14-slim-bookworm

# Copy the application from the builder
COPY --from=builder --chown=app:app /app /app

WORKDIR /app/catalog

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

# Expose port 8000
EXPOSE 8000

# Use gunicorn on port 8000
CMD ["gunicorn", "--bind", ":8000", "--workers", "2", "core.wsgi"]
