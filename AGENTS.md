# AGENTS.md

Rules for AI coding agents working in this repository.

**How these files work.** This root file holds what applies everywhere: commands, ports, safety rules and how
to work alongside other agents. Each area has its own `AGENTS.md` next to its code, which agents read when they
work there. When two files disagree, the one closest to the code being changed wins. A direct instruction from
the user overrides both. Every `AGENTS.md` has a `CLAUDE.md` beside it that holds only `@AGENTS.md`, because
Claude Code reads `CLAUDE.md` files; never put rules in a `CLAUDE.md` (`backend/tests/test_agent_docs.py`).

| Area | File |
|---|---|
| Both backend services: service boundary, API rules, settings, auth, metrics, cache, parity suites | [`backend/AGENTS.md`](backend/AGENTS.md) |
| `catalog` (FastAPI), Celery | [`backend/catalog/AGENTS.md`](backend/catalog/AGENTS.md) |
| `instances` (.NET), dashboard | [`backend/instances/AGENTS.md`](backend/instances/AGENTS.md) |
| React SPA | [`frontend/AGENTS.md`](frontend/AGENTS.md) |
| k6, Prometheus/Grafana, baselines and the `/load-tests` page | [`loadtest/AGENTS.md`](loadtest/AGENTS.md) |
| Docker files, Pulumi, Ansible | [`infra/AGENTS.md`](infra/AGENTS.md) |

A new rule goes in the file for the area it governs. Only rules that apply across areas go here. Add a rule when
an agent gets something wrong that the code and tests do not make obvious, and delete rules that no longer
change what an agent does.

---

## What this repo is

**SAAS_experimental**, a FastAPI + ASP.NET Core + React project created from the `django_react_template`
starter, as a decoupled monorepo:

- **`backend/`**: two services, each with its own PostgreSQL database: `catalog` on FastAPI (Python 3.14,
  Celery + Redis, a uv workspace with `common`) and `instances` on ASP.NET Core (.NET 10, `backend/instances/`).
  Both began as Django and keep the tables and API Django left: `catalog` moved in #34 to #38, `instances`
  in #40 to #45
- **`infra/gateway/`**: nginx route table that gives both services one public origin
- **`frontend/`**: React 19 SPA (TypeScript, Vite, TanStack Router + Query)
- **`infra/docker/`**: Dockerfiles and compose files for both halves

The services expose only `/api/` endpoints publicly, and `/internal/` to each other. The frontend consumes them
over HTTP. The two halves share no code. The API contract is the only interface between them.

Prefer documented conventions over one-off solutions.

| You need | Read |
|----------|------|
| Setup, endpoints and request/response shapes | [`README.md`](README.md) (Quick Start, API) |
| Env vars | [`.env.example`](.env.example) |
| JWT handling | `frontend/src/api/client.ts`, `backend/catalog/catalog/auth.py` (signs), `backend/instances/src/Instances.Api/Auth/OwnerAuth.cs` (`instances` verifies) |
| How the services talk, in the app | `frontend/src/routes/_authed/service-interface.tsx` (`/service-interface`, hand-written, #27) |
| Active / finished plans | GitHub issues labelled `plan` (`gh issue list --label plan [--state closed]`) |

---

## Never do without explicit confirmation

- Git: no write operations (`add`, `commit`, `push`, `merge`, `rebase`, branch `checkout` /
  `switch`, `branch -D`). Make the change and give the user the commands to run. Never run
  `git stash`, `git checkout -- <file>`, `git restore`, `git reset` or `git clean`: they discard
  other agents' work.
- Files: `rm -rf` on non-temporary directories, deleting migration files.
- Infrastructure: `docker compose down -v` or `just db-reset` (destroy DB volumes), editing
  shared `.env` files.
- Shared services: restarting, stopping or resetting Postgres, Redis, Celery or the dev servers
  (`just down`, `just up`, `just compose restart|stop|down`).
- Process: bypassing hooks (`--no-verify`), dropping or truncating tables directly.

`.claude/settings.json` allows all `Bash(*)` commands to keep the dev loop free of prompts.
The list above still applies. The allowlist removes prompts, not judgement.

---

## Commands

The [`justfile`](justfile) holds only day-to-day commands. Run `just` to list them. Do not add
recipes for one-off or rare tasks; document the raw command in the area's `AGENTS.md` instead. A new recipe
gets a `# doc comment` line, then `[group('<area>')]` (`dev`, `docker`, `backend`, `frontend`,
`loadtest`, `infra`, `database`), then the recipe. The comment must come before the attribute, or `just` fails with
"Extraneous attribute". Helpers that other recipes call are marked `[private]`: hidden from the
list but still runnable by name.

```bash
just dev            # db + redis + celery (docker) + backend + frontend dev servers
just install        # uv sync + npm install
just up / down      # everything via docker compose
just compose <args> # any docker compose command against the dev stack

just be-migrate
just be-makemigrations <app>
just be-superuser   # from DJANGO_SUPERUSER_* in .env
just be-test        # catalog's pytest, both API suites, instances' xUnit, repo checks
just be-lint        # ruff check (note: pyproject sets fix = true, so this rewrites files)
just be-fmt         # ruff format

just fe-test        # vitest
just fe-lint        # eslint
just fe-build       # type-check + build

just db-reset       # DESTRUCTIVE: drops the Postgres volume, then re-migrates

just loadtest-up    # load-test stack: prod backend + Postgres + Prometheus + Grafana (#9)
just loadtest-seed --owners 5 --questionnaires-per-owner 200
just k6 <scenario> [KEY=VALUE…]  # smoke load stress soak respondent pdf outage catalog
just loadtest-down  # keeps its volumes

just infra-test     # Pulumi program tests (mocks, no Proxmox)
just infra-preview  # preview the LXC containers, save the plan
just infra-up       # apply exactly the saved plan
just infra <args>   # any pulumi command on the loadtest stack
just converge [--tags app] [--check --diff]  # Ansible: configure the containers
just k6 <scenario> TARGET=lxc  # run from saas-loadgen through saas-gateway
```

Agents run every test command, recipes included, under the machine-wide test lock. See
"Working alongside other agents". Service-specific commands (single suites, migrations, lint, type checks) are
in each area's `AGENTS.md`. Cross-cutting ones:

| Task | Command |
|---|---|
| Backend dev servers only | `just be-dev` (private helper: gateway router :8005, catalog :8006, instances :8007 under `dotnet watch`) |
| Frontend dev server only | `just fe-dev` (private helper, :5174) |
| Logs | `just compose logs -f <service>` |
| Rebuild images | `just compose build [service]` |
| psql shell | `just compose exec db psql -U appuser -d appdb` |
| Move data from a database from before the split | See "Moving a pre-split database" in `README.md` |

### Local services and ports

Host ports are offset so they do not clash with a locally installed Postgres or Redis.

| Service | Host port | Notes |
|---|---|---|
| `db` | `5435` -> 5432 | Postgres 16 (`appuser` / `apppassword` / `appdb`) |
| `redis` | `127.0.0.1:6380` -> 6379 | Celery broker (db 0) and cache (db 1). Loopback only: see Cache in `backend/AGENTS.md` |
| `db` (`instances_db`) | `5437` -> 5432 | The `instances` database (`instancesdb`). `db` above is `catalog`'s |
| e2e `instances` database | `127.0.0.1:5447` | Throwaway Postgres in Docker, `npm run e2e:integration` only (#44) |
| `gateway` | `8005` | One public origin, so `VITE_API_BASE_URL` stays valid |
| `catalog` | `8006` | uvicorn `--reload` |
| `instances` | `8007` | `dotnet watch` (rebuilds on every edit) |
| `relay_outbox` | none | Retries undelivered events |
| `celery_worker`, `celery_beat` | none | `catalog.celery_app`; beat's schedule is code (`beat_schedule`) |
| `frontend` | `5174` | Vite dev server |
| e2e gateway, catalog, instances, frontend | `8015`, `8016`, `8017`, `5184` | Started by `npm run e2e:integration` only (dev + 10) |
| load-test `gateway`, `prometheus`, `grafana` | `8095`, `9095`, `3005` | `just loadtest-up` only; bound to 127.0.0.1 |

The justfile passes `-f infra/docker/docker-compose.yml -p <repo folder name>`. Run other compose commands
through `just compose <args>` rather than bare `docker compose`. Without `-p` the project is named
`docker` and you get a second set of containers and volumes. Docker file layout: `infra/AGENTS.md`.

---

## Working alongside other agents

Other agents may edit this working tree at the same time.

- Claims live in `.agents/claims.md` (repo root). Before editing a file, check it. If another
  agent claimed the file, stop and tell the user. Otherwise add `<file path> - <task>`, and
  remove your lines when done.
- Only edit files your task needs. Changes you did not make belong to another agent. Leave them
  alone.
- Re-read a file immediately before editing it. If an edit fails because the file changed, re-read
  and retry. Never overwrite the whole file.
- Lint, format and test only what you changed. Report failures in code you did not touch, but do
  not fix them. `just be-lint` and `just be-fmt` rewrite the whole backend (`fix = true`), so run
  them only when asked. Scoped lint and format:

  ```bash
  cd backend && uv run ruff check <paths> && uv run ruff format <paths>
  cd backend/instances && dotnet format --include <paths>
  cd frontend && npx eslint <paths>
  ```

- Run only one type of testing (backend, frontend or Playwright) at a time on a machine, across
  all agents. Running them together, or running tests from several agents at once, has crashed
  low-RAM machines.
- Run every test command under the machine-wide lock. If another agent holds the lock, your command
  waits, so set a tool timeout long enough to cover the wait:

  ```bash
  cd backend && flock -o /tmp/agent-tests.lock uv run pytest -q -x <service>/<path>[::<test>]
  cd backend/instances && flock -o /tmp/agent-tests.lock dotnet test   # counts as backend
  cd frontend && flock -o /tmp/agent-tests.lock npx vitest run --reporter=dot <paths>
  cd frontend && flock -o /tmp/agent-tests.lock npm run e2e -- --workers=1
  cd frontend && flock -o /tmp/agent-tests.lock npm run e2e:integration -- --workers=1
  flock -o /tmp/agent-tests.lock just be-test   # same for fe-test and infra-test
  ```

  The quiet flags keep output short; failures still print in full. Filter long logs with `tail` or
  `grep`, never in a way that hides a failure.

- Wrap a recipe in the lock from outside. Never put `flock` inside a recipe: an agent's outer lock
  would then block the recipe's inner lock, and the command would wait forever.
- A local `just k6` run takes the lock too. `TARGET=lxc` runs k6 on saas-loadgen, so it does not.
- Always pass `--workers=1` to Playwright. Its configs leave the worker count open for people, so
  the flag is what limits an agent's run.
- Playwright reuses servers where the suite allows it. The mocked suite needs only Vite: it reuses
  a server on :5174, or starts one and stops it when the run ends. The integration suite never
  reuses servers (see "Testing" in `frontend/AGENTS.md`). It starts its own on separate ports, inside the
  locked command, and stops them when the run ends. Start no other servers for either suite.
- Always pass an app to `just be-makemigrations <app>`. Do not run `just dev` or `just be-dev`:
  they start shared dev servers.
- At the end, list every file you changed so the user can commit them separately.

---

## General rules

- Backend and frontend communicate only through the API contract. Never mix their concerns.
- Never commit `.env` files. `.env.example` is the source of truth for required vars.
- There is exactly one env file: `.env` in the repo root, from `.env.example` (`cp .env.example .env`).
  Both services, Vite, docker-compose (`env_file`), direnv (a local, gitignored `.envrc`) and VS Code all read it.
  Do not add per-folder `.env` files. Add new vars to the root `.env.example`, grouped under the
  backend or frontend heading.
- There is exactly one `.gitignore`, in the repo root. Do not add per-folder `.gitignore` files.
  Scope folder-specific rules with a path prefix (`frontend/dist/`, `backend/.venv/`). The
  `.gitignore` files that ruff, pytest and mypy write inside their own cache folders are
  untracked tool output; leave them.
- Prefer explicit, readable code over clever code.

---

## Docs

There is no `docs/` folder. Docs travel with code in the same change:

| File | Holds |
|---|---|
| `README.md` | Quick start, local setup, the API table, project structure, tech stack |
| `AGENTS.md` (this file and one per area) | Conventions and rules for agents |

Two folders also hold their own records: `backend/contracts/README.md` explains the contract files
beside it, and `loadtest/baselines/` holds measured results.

- A new or changed endpoint updates the API table in `README.md`: method, path, auth (public or
  JWT), request body, response shape with status code. Note non-obvious error behaviour below
  the table.
- Changed setup steps or ports update the Quick Start in `README.md` and the ports table here.
- A changed convention updates the `AGENTS.md` for its area.
- A new nested `AGENTS.md` gets a `CLAUDE.md` beside it holding only `@AGENTS.md`, and a row in the table at the
  top of this file.
- New env vars go in `.env.example` with a comment.
- If you find an outdated doc, fix it in the same change.

---

## Plans (GitHub issues)

Any change touching more than one file needs a plan issue before implementation.

- Create it with labels `plan` + `status: draft`. Once per repo, create the labels first:
  `gh label create plan --force`, `gh label create "status: draft" --force`,
  `gh label create "status: in-progress" --force`. Then:
  `gh issue create --title "Plan: <feature>" --label plan --label "status: draft" --body-file <file>`.
  Write the body file outside the repo.
- The body has these sections: **Goal** (one paragraph), **Background**, **Phases** (each with an
  **Outcome** line, task checkboxes and a **Validation** block), **Testing**, **Risks & Notes**.
- Plans are phased. Each phase is **stable**: it leaves the repo working (migrations applied,
  existing suites green, nothing half-wired).
- Each phase's **Validation** names the tests (file + test name) and manual steps that prove it
  landed. Progress is measured by those checks passing. If a step can only be verified after a
  later phase, merge it into that phase.
- The plan-level **Testing** section covers cross-cutting strategy and the end-to-end
  walkthrough.
- When work starts, swap `status: draft` for `status: in-progress`
  (`gh issue edit <n> --remove-label "status: draft" --add-label "status: in-progress"`).
- When a phase lands, tick its boxes in the issue body (`gh issue edit <n> --body-file <file>`)
  and comment with the validation results (`gh issue comment <n> --body "..."`).
- When all phases are done, close the issue as completed (`Closes #<n>` in the final PR, or
  `gh issue close <n> --reason completed`). Close abandoned plans as `not planned` with a reason.
- Reference the issue (`#<n>`) in related commits and PRs. Never delete plan issues.
- Run a phase's **Validation** and confirm it passes before starting the next phase. Say what
  you ran and the result.
- For a larger feature, create a GitHub milestone for the feature. Each plan in it is its own
  `plan` issue with stable phases, as above, linked to the milestone.
