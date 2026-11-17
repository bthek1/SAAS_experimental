# backend/instances_Django/AGENTS.md

`instances` on Django REST Framework, as it was when .NET replaced it (#40 to #45, last at `19558f1^`), kept
beside the .NET version (#51). Read with the root [`AGENTS.md`](../../AGENTS.md) and
[`backend/AGENTS.md`](../AGENTS.md), which hold the rules both services share.

**It is not deployed.** The dev stack, Docker images, Ansible and Playwright all run `instances_NET`. This copy
exists to compare against: it has its own tests, and `backend/parity_instances/` runs against it with
`INSTANCES_IMPL=django`. Same API, same `instancesdb` schema, same env var names.

## Commands

From `backend/instances_Django/`, tests under the test lock (they count as backend testing):

| Task | Command |
|---|---|
| Tests (SQLite, no Docker) | `uv run pytest` |
| The shared API suite against it | `cd .. && INSTANCES_IMPL=django uv run pytest parity_instances` |
| Any management command | `uv run python manage.py <cmd>` (`SETTINGS`: `dev` by default, `test`, `prod`, `loadtest`; e2e is `DJANGO_SETTINGS_MODULE=core.settings.e2e`) |

## Layout

- `apps/questionnaires/`: models, serializers, views, `refs.py` (type copies, the rules `Refs/RefService.cs` was
  ported from), `dashboard.py`, `pdf.py` (WeasyPrint, so hosts need Pango), management commands
  (`seed_loadtest`, `reconcile_refs`, `import_from_monolith`), and its tests beside them.
- `core/`: settings profiles (`core.settings.<profile>`), URLs, WSGI.
- `shared/`: the Django infrastructure that lived in `common` until #45 (`cache`, `owned`, `peers`, `metrics`,
  `pagination`, `settings/`). Of `common` it still reads only `dev_keys` and `gunicorn_conf`, as `catalog` does;
  `tests/test_service_boundary.py` holds both to that.

## Rules

- **The schema is shared with .NET.** Its migrations are the DDL .NET's `Baseline` migration copied. A schema
  change belongs in .NET's EF migrations first; mirror it here only if the parity suite needs it.
- `parity_instances` pins the API for both implementations. A test that Django fails because of behaviour .NET
  added after #45 is marked `xfail` under Django with the reason, never deleted.
- Django and its tools stay out of `catalog` and `common`: they are this member's dependencies only.
