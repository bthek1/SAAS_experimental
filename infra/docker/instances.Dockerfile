# Build context is backend/.
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PROJECT_ENVIRONMENT=/venv
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System libraries for WeasyPrint (PDF export) and a font, since slim images ship none
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for layer caching
COPY pyproject.toml uv.lock .python-version ./
COPY common/pyproject.toml common/pyproject.toml
COPY catalog/pyproject.toml catalog/pyproject.toml
COPY instances/pyproject.toml instances/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-workspace --no-dev --package instances

# Copy project source
COPY . /app

# Install the shared package
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package instances

ENV PATH="/venv/bin:$PATH"

WORKDIR /app/instances

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
