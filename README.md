# test_repo

A decoupled web application, created from the `django_react_template` starter:

- **`backend/`** — Django REST Framework API (Python 3.14, PostgreSQL, Celery)
- **`frontend/`** — React 19 SPA (TypeScript, Vite, TanStack Router, TanStack Query)

---

## Quick Start

```bash
# 1. Clone
git clone git@github.com:bthek1/test_repo.git && cd test_repo

# 2. Create the env file (one .env in the repo root, shared by backend and frontend)
cp .env.example .env

# 3. Start everything (compose files live in infra/docker/)
just up

# 4. Run migrations (first time), in a second terminal
just compose exec backend python manage.py migrate
```

`just compose <args>` runs any `docker compose` command against `infra/docker/docker-compose.yml`
with the project name set to the repo folder name (lowercased). Without `just`, pass the same
`-f` and `-p` flags yourself. Leaving out `-p` makes Compose name the project `docker`, after the
compose file's folder, and create a separate set of containers and volumes.

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5174 |
| Backend API | http://localhost:8005/api/ |
| Django admin | http://localhost:8005/admin/ |
| Health check | http://localhost:8005/api/health/ |
| Flower (Celery UI) | http://localhost:5555 (`cd backend && uv run celery -A core flower --port=5555`) |

---

## Local development without Docker

```bash
cp .env.example .env
just install            # uv sync + npm install
just dev                # db + redis + celery in Docker, backend and frontend locally
```

The backend runs on `:8005` and the frontend on `:5174`. Run `just --list` for every command.

---

## API

All endpoints are under `/api/`. Authenticated endpoints need `Authorization: Bearer <access>`.

| Method | Path | Auth | Body | Response |
|--------|------|------|------|----------|
| `POST` | `/api/token/` | Public | `{email, password}` | `200 {access, refresh}` |
| `POST` | `/api/token/refresh/` | Public | `{refresh}` | `200 {access, refresh}` (refresh tokens rotate) |
| `POST` | `/api/accounts/register/` | Public | `{email, password}` (password min 8) | `201 {id, email}` |
| `GET` | `/api/accounts/me/` | JWT | | `200 {id, email, first_name, last_name, date_joined}` |
| `PUT` / `PATCH` | `/api/accounts/me/` | JWT | `{first_name?, last_name?, email?}` | `200` same shape as `GET` |
| `GET` | `/api/health/` | Public | | `200 {status: "ok"}` |
| `POST` | `/api/tasks/trigger/` | Public | any JSON object | `202 {task_id}` |
| `GET` | `/api/tasks/<task_id>/` | Public | | `200 {task_id, status, result, traceback}` |
| `POST` | `/api/tasks/<task_id>/revoke/` | Public | `{terminate?: bool}` | `200 {task_id, revoked: true}` |

- Validation errors return `400` with DRF's `{field: [messages]}` shape. Missing or bad JWTs return `401`.
- The `/api/tasks/` endpoints are a Celery demo (`apps/utils/tasks.py`). They are public so the
  demo works without login. Add auth before reusing them.
- Task `status` is a Celery state (`PENDING`, `STARTED`, `SUCCESS`, `FAILURE`, `REVOKED`, ...).
  `result` is set only on `SUCCESS` and `traceback` only on `FAILURE`. An unknown `task_id`
  returns `PENDING`.

---

**AI assistants:** [AGENTS.md](AGENTS.md) holds all agent rules. `CLAUDE.md` only imports it (`@AGENTS.md`). Add new rules to `AGENTS.md`, not anywhere else.

---

## Project Structure

```
/
├── backend/          Django REST API
│   ├── core/         Settings, URLs, WSGI
│   ├── apps/         Domain applications
│   │   ├── accounts/ User model (email-based), registration, JWT auth
│   │   └── utils/    Health check, Celery task demo endpoints
│   ├── tests/        Repo-level tests (infra/docker layout)
│   └── manage.py
├── frontend/         React SPA
│   └── src/
│       ├── api/      Axios client, query keys, API functions
│       ├── components/ui/  shadcn/ui components
│       ├── hooks/    Custom hooks (auth, etc.)
│       ├── lib/      cn() helper, date-fns wrappers
│       ├── routes/   TanStack Router file-based routes
│       ├── schemas/  Zod validation schemas
│       ├── store/    Zustand global state slices
│       └── types/    TypeScript types from API contracts
├── infra/docker/     Dockerfiles + compose files (dev stack, prod backend)
└── AGENTS.md         Rules for AI coding agents
```

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend language | Python 3.14 |
| Backend framework | Django 6 + Django REST Framework |
| Auth | JWT (`djangorestframework-simplejwt`) |
| Database | PostgreSQL 16 |
| Async tasks | Celery + Redis (`django-celery-results`, `django-celery-beat`) |
| Dependency manager | [uv](https://github.com/astral-sh/uv) |
| Frontend language | TypeScript |
| Frontend bundler | Vite |
| UI framework | React 19 |
| Routing | TanStack Router |
| Server state | TanStack Query v5 |
| HTTP client | Axios |
| Styling | Tailwind CSS v4 + shadcn/ui |
| Forms | React Hook Form + Zod |
| Global state | Zustand |
| Testing (frontend) | Vitest + React Testing Library + MSW |
| Utilities | date-fns, ECharts, Recharts, react-markdown |
| Container | Docker Compose |
| Task runner | [just](https://github.com/casey/just) |
