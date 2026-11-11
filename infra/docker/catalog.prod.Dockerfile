# Build context is backend/ — from the repo root run:
#   docker build -f infra/docker/catalog.prod.Dockerfile backend
# catalog runs on FastAPI (#37); backend/catalog/ is the Django version, kept until #38.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY common/pyproject.toml common/pyproject.toml
COPY catalog/pyproject.toml catalog/pyproject.toml
COPY catalog_fastapi/pyproject.toml catalog_fastapi/pyproject.toml
COPY instances/pyproject.toml instances/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev --package catalog-fastapi
ADD . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package catalog-fastapi

# Then, use a final image without uv
FROM python:3.14-slim-bookworm

# Copy the application from the builder
COPY --from=builder --chown=app:app /app /app

# gunicorn reads gunicorn.conf.py from here.
WORKDIR /app/catalog_fastapi

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8000

# uvicorn workers under gunicorn. keepalive comes from gunicorn.conf.py (#24).
CMD ["gunicorn", "--bind", ":8000", "--workers", "2", "-k", "uvicorn_worker.UvicornWorker", "catalog_fastapi.app:app"]
