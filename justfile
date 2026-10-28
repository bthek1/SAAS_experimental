# Django + React monorepo justfile
# Only day-to-day commands live here. Run `just` to list them.

set dotenv-load := false

# Clear any shell-activated virtualenv so uv uses the project's own .venv
# (avoids "VIRTUAL_ENV does not match project environment path" warning)

export VIRTUAL_ENV := ""

# Compose files live in infra/docker/. The project name is pinned to the repo folder name
# so containers and the postgres_data volume keep the same names as before the move.

compose := "docker compose -f infra/docker/docker-compose.yml -p " + lowercase(file_name(justfile_directory()))

[private]
default:
    @just --list

# --- Dev ---

# Full local stack: db + redis + celery in Docker, backend and frontend dev servers locally
[group('dev')]
dev: db-up celery-up
    #!/usr/bin/env bash
    echo "Starting backend and frontend dev servers..."
    echo "  Backend : http://localhost:8005"
    echo "  Frontend: http://localhost:5174"
    _pids=()
    _cleanup() {
        echo ""
        for pid in "${_pids[@]}"; do kill "$pid" 2>/dev/null || true; done
        wait 2>/dev/null || true
    }
    trap _cleanup INT TERM EXIT
    if command -v overmind &>/dev/null; then
        overmind start
    else
        just be-dev &
        _pids+=($!)
        just fe-dev &
        _pids+=($!)
        wait "${_pids[@]}"
    fi

# Install backend (uv) and frontend (npm) dependencies
[group('dev')]
install:
    cd backend && uv sync --group dev
    cd frontend && npm install

alias setup := install

# --- Docker ---

# Start all services (db, redis, celery, backend, frontend)
[group('docker')]
up:
    {{ compose }} up

# Stop all services
[group('docker')]
down:
    {{ compose }} down

# Any other compose command against the dev stack: just compose logs -f backend
[group('docker')]
[positional-arguments]
compose *args:
    {{ compose }} "$@"

# --- Backend ---

# Apply database migrations
[group('backend')]
be-migrate:
    cd backend && uv run python manage.py migrate

# Create new migrations after model changes: just be-makemigrations <app>
[group('backend')]
be-makemigrations app="":
    cd backend && uv run python manage.py makemigrations {{ app }}

# Create a Django superuser from DJANGO_SUPERUSER_* in .env
[group('backend')]
be-superuser:
    cd backend && uv run python manage.py createsuperuser --noinput

# Run backend test suite
[group('backend')]
be-test:
    cd backend && uv run pytest

# Lint backend code (ruff check)
[group('backend')]
be-lint:
    cd backend && uv run ruff check .

# Format backend code (ruff format)
[group('backend')]
be-fmt:
    cd backend && uv run ruff format .

# --- Frontend ---

# Run frontend tests
[group('frontend')]
fe-test:
    cd frontend && npm test

# Lint frontend code
[group('frontend')]
fe-lint:
    cd frontend && npm run lint

# Type-check and build the frontend
[group('frontend')]
fe-build:
    cd frontend && npm run build

# --- Database ---

# Reset the database: drops Docker volumes, restarts services, re-applies migrations
[group('database')]
db-reset:
    {{ compose }} down -v
    {{ compose }} up -d
    just be-migrate
    @echo "Database reset complete."

# --- Helpers used by `dev` (hidden from the list, still runnable by name) ---

# Run the Django dev server on :8005 (runs makemigrations + migrate first)
[private]
be-dev: be-makemigrations be-migrate
    cd backend && uv run python manage.py runserver 0.0.0.0:8005

# Run the Vite dev server on :5174
[private]
fe-dev:
    cd frontend && npm run dev -- --host 0.0.0.0 --port 5174

# Start the db container if not already running
[private]
db-up:
    @{{ compose }} ps --status running db | grep -q db \
        && echo "DB already running." \
        || (echo "Starting DB..." && {{ compose }} up -d db && echo "Waiting for DB to be ready..." && sleep 3)

# Start the Redis + Celery worker + beat containers if not already running
[private]
celery-up:
    #!/usr/bin/env bash
    _redis_up=$({{ compose }} ps --status running redis | grep -c redis || true)
    _worker_up=$({{ compose }} ps --status running celery_worker | grep -c celery_worker || true)
    if [[ "$_redis_up" -gt 0 && "$_worker_up" -gt 0 ]]; then
        echo "Redis + Celery worker already running."
    else
        echo "Starting Redis + Celery worker + beat..."
        {{ compose }} up -d redis celery_worker celery_beat
    fi
