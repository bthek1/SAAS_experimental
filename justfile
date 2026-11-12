# FastAPI + Django + React monorepo justfile
# Only day-to-day commands live here. Run `just` to list them.

set dotenv-load := false

# Clear any shell-activated virtualenv so uv uses the project's own .venv
# (avoids "VIRTUAL_ENV does not match project environment path" warning)

export VIRTUAL_ENV := ""

# Compose files live in infra/docker/. The project name is pinned to the repo folder name
# so containers and the postgres_data volume keep the same names as before the move.

compose := "docker compose -f infra/docker/docker-compose.yml -p " + lowercase(file_name(justfile_directory()))

# The local load-test stack (#9): its own project and volumes, never the dev stack's.
loadtest_compose := "docker compose --env-file .env -f infra/docker/docker-compose.loadtest.yml -p " + lowercase(file_name(justfile_directory())) + "-loadtest"

[private]
default:
    @just --list

# --- Dev ---

# Full local stack: db + redis + celery in Docker, backend and frontend dev servers locally
[group('dev')]
dev: db-up celery-up
    #!/usr/bin/env bash
    echo "Starting backend and frontend dev servers..."
    echo "  Gateway : http://localhost:8005 (catalog :8006, instances :8007)"
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
        just be-relay &
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

# Any other compose command against the dev stack: just compose logs -f catalog
[group('docker')]
[positional-arguments]
compose *args:
    {{ compose }} "$@"

# --- Backend ---

# Apply database migrations on both services (catalog: Alembic, adopting a Django-built db)
[group('backend')]
be-migrate:
    cd backend && uv run python -m catalog migrate
    cd backend && uv run python instances/manage.py migrate

# New migration after model changes: just be-makemigrations questionnaires | catalog "<message>"
[group('backend')]
be-makemigrations app message="change":
    #!/usr/bin/env bash
    set -euo pipefail
    cd backend
    case "{{ app }}" in
        questionnaires) uv run python instances/manage.py makemigrations questionnaires ;;
        catalog) cd catalog && uv run alembic revision --autogenerate -m "{{ message }}" ;;
        *) echo "unknown app {{ app }}: questionnaires (instances) or catalog (Alembic)" >&2; exit 1 ;;
    esac

# Create a staff superuser for /admin/ from DJANGO_SUPERUSER_* in .env
[group('backend')]
be-superuser:
    cd backend && uv run python -m catalog create-superuser

# Run the backend test suites: each service, then the repo-level checks
[group('backend')]
be-test:
    cd backend && uv run pytest catalog
    cd backend && uv run pytest parity
    cd backend && uv run pytest instances
    cd backend && uv run pytest tests

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

# --- Load tests (#9) ---

# Per-minute table of one k6 run (throughput, latency, each container's CPU, Postgres)
[group('loadtest')]
k6-report testid:
    python3 loadtest/report.py {{ testid }}

# Start the load-test stack (prod images behind the gateway :8095 + Prometheus :9095 + Grafana :3005)
[group('loadtest')]
loadtest-up:
    {{ loadtest_compose }} up -d --build --wait gateway relay_outbox prometheus grafana

# Stop the load-test stack (keeps its volumes: Prometheus history, seeded DB)
[group('loadtest')]
loadtest-down:
    {{ loadtest_compose }} down

# Seed both load-test services: just loadtest-seed --owners 5 --questionnaires-per-owner 200
[group('loadtest')]
[positional-arguments]
loadtest-seed *args:
    #!/usr/bin/env bash
    set -euo pipefail
    owners=5; per_owner=200
    while [ $# -gt 0 ]; do
        case "$1" in
            --owners) owners="$2"; shift 2 ;;
            --questionnaires-per-owner) per_owner="$2"; shift 2 ;;
            *) echo "unknown option $1" >&2; exit 1 ;;
        esac
    done
    {{ loadtest_compose }} exec catalog python -m catalog seed-loadtest --owners "$owners"
    {{ loadtest_compose }} exec catalog python -m catalog relay-outbox --once
    {{ loadtest_compose }} exec instances python manage.py seed_loadtest --questionnaires-per-owner "$per_owner"

# Run a k6 scenario, results to Prometheus/Grafana: smoke load stress soak respondent pdf outage catalog [KEY=VALUE…]
[group('loadtest')]
[positional-arguments]
k6 scenario *options:
    loadtest/run.sh "$@"

# --- Infra: Proxmox LXC containers for load tests (#9) ---
# Pulumi state is local and per repo. The backend and passphrase are set for each command, so
# `pulumi login` (global) is never needed and other Pulumi projects keep their own backends.

pulumi := "PULUMI_BACKEND_URL=file://" + home_directory() + "/.pulumi-state/saas-experimental PULUMI_CONFIG_PASSPHRASE_FILE=" + env("PULUMI_CONFIG_PASSPHRASE_FILE", home_directory() + "/.pulumi-state/saas-experimental.passphrase") + " VIRTUAL_ENV= pulumi -C infra/pulumi --stack loadtest"

# Any pulumi command on the loadtest stack: just infra config set saas:node bthek1
[group('infra')]
[positional-arguments]
infra *args:
    @{{ pulumi }} "$@"

# Preview the containers and save the plan that infra-up applies
[group('infra')]
infra-preview:
    {{ pulumi }} preview --diff --save-plan .plan.json

# Apply exactly the plan infra-preview saved (nothing else can slip in)
[group('infra')]
infra-up:
    {{ pulumi }} up --plan .plan.json --yes
    rm -f infra/pulumi/.plan.json

# Run the Pulumi program's tests (topology + mocks; no Proxmox needed)
[group('infra')]
infra-test *args:
    cd infra/pulumi && VIRTUAL_ENV= uv run pytest {{ args }}

# Reset the LXC deploy's database to the fixed seed (run before every measured k6 run)
[group('infra')]
loadtest-reset:
    cd infra/ansible && ansible-playbook site.yml --tags app --limit app,instances -e app_reset_db=true

# Configure the containers with Ansible (infra/ansible/site.yml): just converge --tags app --check --diff
[group('infra')]
[positional-arguments]
converge *args:
    cd infra/ansible && ansible-playbook site.yml "$@"

# --- Database ---

# Reset the database: drops Docker volumes, restarts services, re-applies migrations
[group('database')]
db-reset:
    {{ compose }} down -v
    {{ compose }} up -d
    just be-migrate
    @echo "Database reset complete."

# --- Helpers used by `dev` (hidden from the list, still runnable by name) ---

# Run both dev servers (catalog on FastAPI) and the gateway's dev router on :8005 (migrates first)
[private]
be-dev: be-migrate
    #!/usr/bin/env bash
    trap 'kill 0' EXIT
    (cd backend && uv run uvicorn catalog.app:app --host 0.0.0.0 --port 8006 --reload --reload-dir catalog) &
    (cd backend && uv run python instances/manage.py runserver 0.0.0.0:8007) &
    python3 infra/gateway/dev_router.py --port 8005 \
        --service catalog=http://localhost:8006 --service instances=http://localhost:8007 &
    wait

# Retry events the immediate push could not deliver
[private]
be-relay:
    cd backend && uv run python -m catalog relay-outbox

# Run the Vite dev server on :5174
[private]
fe-dev:
    cd frontend && npm run dev -- --host 0.0.0.0 --port 5174

# Start the db container if not already running
[private]
db-up:
    @{{ compose }} ps --status running instances_db | grep -q instances_db \
        && echo "DBs already running." \
        || (echo "Starting DBs..." && {{ compose }} up -d db instances_db && echo "Waiting for DBs to be ready..." && sleep 3)

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
