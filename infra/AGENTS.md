# infra/AGENTS.md

Docker files, the gateway, and the Proxmox LXC load-test deploy. Read with the root [`AGENTS.md`](../AGENTS.md).
k6 and measuring are in [`loadtest/AGENTS.md`](../loadtest/AGENTS.md).

## Commands

```bash
just infra-test     # Pulumi program tests (mocks, no Proxmox); also runs infra/ansible/tests/
just infra-preview  # preview the LXC containers, save the plan
just infra-up       # apply exactly the saved plan
just infra <args>   # any pulumi command on the loadtest stack
just converge [--tags app] [--check --diff]  # Ansible: configure the containers
python3 infra/gateway/build_nginx.py         # regenerate the gateway config after editing routes.json
docker build -f infra/docker/<catalog|instances>.prod.Dockerfile backend   # prod service image
uvx --from 'ansible-lint==25.*' ansible-lint site.yml                       # from infra/ansible/
```

## Docker (`infra/docker/`)

All Docker files live here: `docker-compose.yml` (dev stack), `docker-compose.prod.yml` (gunicorn services +
gateway + dbs), `docker-compose.loadtest.yml` (load tests, its own project `<repo folder name>-loadtest`),
`<service>[.prod].Dockerfile`, and a `<name>.Dockerfile.dockerignore` next to each Dockerfile (BuildKit reads it
in place of the build context's `.dockerignore`). Paths in the compose files are relative to `infra/docker/`.
Put new Docker files here as `<service>[.<variant>].Dockerfile` with a matching `.dockerignore`.
`backend/tests/test_infra_docker.py` enforces this layout.

Inside Compose, the `environment:` blocks set `DATABASE_URL`, `INSTANCES_DATABASE_URL`, `CELERY_BROKER_URL`
and `CACHE_REDIS_URL` to the in-network hosts (`db:5432`, `instances_db:5432`, `redis:6379`). These override the
`localhost` values in the root `.env`.

## Proxmox LXC containers (`infra/pulumi/`)

The load-test deploy (#9, Phases 3 to 5, #13) runs in seven unprivileged LXC containers on the Proxmox
host `192.168.2.70` (node `bthek1`): `saas-catalog` 241 (the `catalog` service; it kept its `app` role and id so
Pulumi never replaces it), `saas-db` 242, `saas-monitor` 243, `saas-loadgen` 244, `saas-cache` 245,
`saas-instances` 246, `saas-gateway` 247. A container's IP is its id as the last octet (`192.168.2.241`…). Pulumi
creates bare containers. Ansible (Phase 4) configures them.

- ⚠️ **Guest ids 241 to 249 only.** Ids are fixed per role in `saas_loadtest/topology.py`, never
  positional: renumbering makes Pulumi *replace* a guest and its data. So does a new name, unless the old one
  stays in `PREVIOUS_NAMES` as an alias. A new hostname reboots the container. 220 to 240 belong to
  the `kubernates_project` repo and are refused. The host's other guests (100 to 209) are unrelated.
- **State is local and per repo**: `~/.pulumi-state/saas-experimental`, passphrase in
  `~/.pulumi-state/saas-experimental.passphrase`. The justfile sets `PULUMI_BACKEND_URL` and
  `PULUMI_CONFIG_PASSPHRASE_FILE` per command. Never run `pulumi login`: it is global and would
  repoint other projects. Use `just infra <args>`, not bare `pulumi`.
- `Pulumi.loadtest.yaml` is gitignored. `Pulumi.loadtest.yaml.example` documents every key, and
  the one-time setup, including a dedicated API token scoped to a `saas-loadtest` pool. For now
  the stack uses kubernates_project's token (copied, encrypted, 2026-11-02) and no pool.
  Revoking that token breaks both stacks.
- Containers are unprivileged with `nesting=1` (the Proxmox default; systemd needs it) and
  `keyctl=0`, so Docker cannot run inside. Install services natively. `test_program.py` enforces
  this, and that root logs in by SSH key only.
- `infra-up` applies only the plan `infra-preview` saved. Read the preview, especially any
  replace or delete, before applying.
- The pulumi venv is Python 3.13 (`pulumi-proxmoxve` is not on 3.14 yet), separate from `backend/`.

## Ansible (`infra/ansible/`, `just converge`)

Configures the containers. Roles are `common` (all), `postgres` (saas-db), `redis` (saas-cache), `app`
(saas-catalog and saas-instances, told apart by `app_service` and `app_unit` in `group_vars`), `gateway`
(saas-gateway), `monitor` (saas-monitor) and `loadgen` (saas-loadgen). The inventory (`inventory/pulumi.py`)
reads the Pulumi stack outputs, secrets included, and refuses any non-private address. Nothing secret is stored
in the repo.

- Everything is installed natively, with no Docker:
  - `catalog`: the working tree rsynced to `/srv/app/backend` (without `instances/`), `uv sync --package
    catalog` (Python 3.14), gunicorn with uvicorn workers under systemd (`saas-app.service`), and
    `saas-relay.service`, which retries events (`roles/app/tasks/python.yml`);
  - `instances` (#44, #45): the ASP.NET Core runtime in `/opt/dotnet` (pinned by version and sha256), the
    service published on the control host (`dotnet publish` into the gitignored `backend/instances/publish/`,
    needing the SDK there) and rsynced to `/srv/app/instances-dotnet`, run by `saas-instances.service` on
    Kestrel. No Python. Its commands are verbs of the binary (`migrate`, `reset-db`, `clear-cache`,
    `seed-loadtest`). `app_commands` in `roles/app/defaults/main.yml` holds each service's commands, and env
    is in `/etc/<unit>/app.env`;
  - nginx from apt on saas-gateway, its config from `infra/gateway/build_nginx.py --address ...`;
  - saas-db holds `catalogdb` and `instancesdb` with separate login roles. The monolith's `appdb` is still
    there, unused, as a way back;
  - Postgres 16 and Redis from apt (Redis: no RDB or AOF, `maxmemory` + `allkeys-lru`);
  - Prometheus, Grafana, node_exporter, postgres_exporter, redis_exporter, k6 and uv as release binaries
    pinned by version **and sha256** in `group_vars/all.yml`. Bump both together.
- A second run must report `changed=0`, and `--check --diff` must show nothing. A task that
  always reports changed hides real changes: fix it rather than ignore it. `ansible-lint`
  (production profile) passes.
- **Firewall:** nftables, input default-deny, per group in `group_vars/<group>.yml`. SSH only from
  `admin_hosts`. A service's port admits only the gateway, its peer service and the scraper, so
  `/internal/` is unreachable from anywhere else, and k6 and you go through the gateway. Never enable the
  Proxmox datacenter firewall for this (it covers the whole host).
- **CPU and memory per container come from its cgroup**, not node_exporter. Inside an LXC,
  `/proc/stat` counts the host's work on the container's cores (an idle container read 16 %
  busy). `roles/common/files/container-metrics.sh` writes `container_*` metrics to node_exporter's
  textfile collector every 5 s. Read memory as the working set: `memory.current` includes page
  cache.
- The Grafana datasource URL is `${PROMETHEUS_URL}` (compose: `http://prometheus:9090`,
  saas-monitor: `http://localhost:9090`). Rules, provisioning and dashboards are the same files
  as the local stack's.
- `TARGET=lxc` runs k6 on saas-loadgen, through saas-gateway. `/root/k6.env` (written by `roles/loadgen`) holds
  `BASE_URL`, `OWNERS`, the owner password and the remote-write settings, so `run.sh` passes no
  secret on a command line. Grafana is `http://192.168.2.243:3000` (user `admin`, password:
  `just infra stack output grafana_admin_password --show-secrets`).
