# backend/catalog/AGENTS.md

`catalog` on FastAPI (#35 to #38). Read with the root [`AGENTS.md`](../../AGENTS.md) and
[`backend/AGENTS.md`](../AGENTS.md), which hold the rules both services share.

The package is `backend/catalog/catalog/`; tests are in `backend/catalog/tests/`, Alembic config in
`backend/catalog/alembic.ini`.

## Commands

From `backend/`, tests under the test lock:

| Task | Command |
|---|---|
| Tests | `uv run pytest catalog` |
| Coverage | `uv run pytest catalog --cov=catalog --cov-report=term-missing` |
| Type check | `uv run mypy catalog common` |
| Any command | `uv run python -m catalog <cmd>` |
| New migration | `just be-makemigrations catalog "<message>"` (Alembic autogenerate against the dev db; read the result) |
| Staff account for `/admin/` | `just be-superuser` (`python -m catalog create-superuser`, from `DJANGO_SUPERUSER_*`) |
| Celery worker outside Docker | `uv run celery -A catalog.celery_app worker --loglevel=info` |
| Flower UI on :5555 | `uv run celery -A catalog.celery_app flower --port=5555` |

## Rules

- **Same contract as the Django version had** (see "API rules" in `backend/AGENTS.md`). Never FastAPI's 422:
  bodies go through `errors.parse()`. Timestamps are `...123456Z` in responses and `+00:00` in events.
- **Layout.** `routers/` (thin), `schemas.py` (Pydantic bodies and response dicts), `services.py` (all
  writes), `events.py` (outbox), `models.py`, `auth.py`, `cache.py`, `metrics.py`, `admin.py`
  (sqladmin), `celery_app.py`, `__main__.py` (commands). Business logic goes in `services.py`.
  Endpoints return `responses.json_response(...)`, never a dict: FastAPI walks a returned dict
  through `jsonable_encoder`, ~10 times the cost of encoding it (#41). A returned Response skips the
  decorator's `status_code`, so a create passes 201 itself. `cache.cached()` returns the body as bytes.
- **Database.** SQLAlchemy 2, sync sessions, one per request (`db.get_session`). The tables are the
  ones Django created, with Django's names; `models.py` explains. Django's `on_delete` was never in the
  database, so `services.py` does CASCADE and RESTRICT by hand. Work that must wait for the commit goes
  through `db.on_commit()`. Postgres connections set `client_encoding=utf8` and `TimeZone=UTC`: the LXC
  databases are `SQL_ASCII`. No `pool_pre_ping`: a connection is pinged only after `PING_AFTER_IDLE`
  seconds in the pool, and replaced if dead (#41).
- **Never hold a connection while waiting or doing slow work** (#38). The pool has 15 connections
  per worker (`db.POOL_SIZE + db.POOL_OVERFLOW`), and `app.py` caps AnyIO's threads at the same
  number, so extra requests queue for a thread instead of failing on the 30 s pool timeout. Keep
  that cap if the pool changes. A dependency that queries ends its transaction before it returns,
  as `auth.current_user` does, or a request waits for the endpoint's thread holding a connection.
  End the transaction before CPU-heavy work too: `authenticate` commits before the pbkdf2 hash, and
  `create_user` hashes before its first query. Both once failed requests on a stress run's login
  burst. `tests/test_pool_deadlock.py` reproduces each with 2 threads and 1 connection.
- **Migrations.** Alembic, revision 0001 is the schema Django left. `python -m catalog migrate` stamps a
  Django-built database at 0001 by itself, then upgrades. Never edit an applied revision.
  `tests/catalog_django_schema.txt` is 0001's schema, frozen from Django's while both existed: never
  regenerate it to make a test pass.
- **Settings.** `settings.py` (pydantic-settings) reads the env and the root `.env`, with the rules under
  "Settings" in `backend/AGENTS.md`.
- **Auth.** `auth.py` signs RS256 tokens with simplejwt's claims and lifetimes, and stores passwords
  in Django's `pbkdf2_sha256` format at Django 6.0's iteration count, so `instances` and old hashes
  keep working. `tests/test_catalog_compat.py` checks both against values frozen from Django.
- **Metrics.** As under "Metrics and load tests" in `backend/AGENTS.md` (`metrics.py`, `db.py`).
- **Server.** gunicorn with `-k uvicorn_worker.UvicornWorker`, which passes gunicorn's `keepalive` on to
  uvicorn (#24). `gunicorn_threads` does not apply: sync endpoints run in uvicorn's thread pool, and
  SQLAlchemy pools 5 connections (15 under load) per worker.
- **Tests.** `catalog/tests/` on in-memory SQLite (`Base.metadata.create_all`), with `RecordingInstances`
  for the peer and `cache_on` (an in-memory Redis stand-in). `test_app.py` builds the app with other
  settings (HTTPS redirect, hosts, CORS); the parity suite covers the API itself. Postgres checks
  (0001 against Django's frozen schema, adopting a Django-built database, Alembic against the models,
  concurrent writers, a `SQL_ASCII` database) are in `tests/test_catalog_schema.py`; Django compatibility
  (hashes, token claims, seed ids, all frozen) in `tests/test_catalog_compat.py`. `tests/test_observability.py`
  checks the dashboards read both metric families and that the latency buckets match django-prometheus's.
  `infra/ansible/tests/test_app_role.py` checks every command the app role runs is defined.

## Celery

- `catalog` only. App and tasks in `catalog/celery_app.py` (`@app.task`).
- Broker is Redis. Results are stored in Postgres through Celery's SQLAlchemy backend
  (`celery_taskmeta`). Periodic schedules are code: `beat_schedule` in the same file.
- The test profiles run tasks eagerly, with an in-memory broker, so tests need no Redis.
- The SPA polls task state with `frontend/src/hooks/useTaskPoller.ts`.
