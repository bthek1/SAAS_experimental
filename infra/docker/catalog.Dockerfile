# Build context is backend/. catalog runs on FastAPI (#35 to #38).
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/venv
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first for layer caching. uv needs every workspace member's
# pyproject.toml, even for one package.
COPY pyproject.toml uv.lock .python-version ./
COPY common/pyproject.toml common/pyproject.toml
COPY catalog/pyproject.toml catalog/pyproject.toml
COPY instances/pyproject.toml instances/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev --package catalog

# Copy project source
COPY . /app

# Install the workspace packages
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package catalog

ENV PATH="/venv/bin:$PATH"

WORKDIR /app/catalog

EXPOSE 8000

CMD ["uvicorn", "catalog.app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
