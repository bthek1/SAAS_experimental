"""Guards for the Docker layout in infra/docker/.

Static checks read the files directly. The compose checks run `docker compose config`,
which resolves every relative path the same way `docker compose up` does, and skip
without Docker. The whole module skips when infra/ is absent (e.g. inside the backend
image).
"""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKER_DIR = REPO_ROOT / "infra" / "docker"
DEV_COMPOSE = DOCKER_DIR / "docker-compose.yml"
PROD_COMPOSE = DOCKER_DIR / "docker-compose.prod.yml"
COMPOSE_FILES = [DEV_COMPOSE, PROD_COMPOSE]

# Host ports documented in AGENTS.md ("Local services and ports").
DEV_HOST_PORTS = {"db": "5435", "redis": "6380", "backend": "8005", "frontend": "5174"}

# Folders that never hold project files.
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}

pytestmark = pytest.mark.skipif(
    not DOCKER_DIR.is_dir(), reason="infra/docker not present"
)

requires_docker = pytest.mark.skipif(
    shutil.which("docker") is None, reason="docker CLI not installed"
)


def _compose_config(compose_file: Path) -> dict[str, Any]:
    # Fixed argv; docker is resolved from PATH like every other dev command.
    cmd = ["docker", "compose", "-f", str(compose_file), "config", "--format", "json"]
    result = subprocess.run(  # noqa: S603
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if "unknown" in result.stderr and "compose" in result.stderr:
            pytest.skip("docker compose plugin not installed")
        pytest.fail(
            f"docker compose config failed for {compose_file.name}:\n{result.stderr}"
        )
    config: dict[str, Any] = json.loads(result.stdout)
    return config


def _project_files(pattern: str) -> list[Path]:
    return [
        path
        for path in REPO_ROOT.rglob(pattern)
        if not SKIP_DIRS.intersection(path.relative_to(REPO_ROOT).parts)
    ]


# --- Static checks ---


def test_compose_files_exist() -> None:
    for compose_file in COMPOSE_FILES:
        assert compose_file.is_file(), f"missing {compose_file.relative_to(REPO_ROOT)}"


def test_every_dockerfile_has_a_dockerignore_that_excludes_env() -> None:
    dockerfiles = sorted(DOCKER_DIR.glob("*.Dockerfile"))
    assert dockerfiles, "no *.Dockerfile in infra/docker"
    for dockerfile in dockerfiles:
        ignore = dockerfile.with_name(f"{dockerfile.name}.dockerignore")
        assert ignore.is_file(), f"{dockerfile.name} has no {ignore.name}"
        patterns = ignore.read_text().split()
        assert ".env" in patterns, f"{ignore.name} must exclude .env"


def test_no_docker_files_outside_infra() -> None:
    stray = [
        path.relative_to(REPO_ROOT)
        for pattern in (
            "Dockerfile",
            "*.Dockerfile",
            ".dockerignore",
            "docker-compose*.yml",
            "compose*.yml",
        )
        for path in _project_files(pattern)
        if DOCKER_DIR not in path.parents
    ]
    assert not stray, f"Docker files belong in infra/docker/: {stray}"


def test_env_file_paths_point_at_root_env() -> None:
    for compose_file in COMPOSE_FILES:
        paths = re.findall(
            r"^\s*-?\s*path:\s*(\S+)\s*$", compose_file.read_text(), re.MULTILINE
        )
        assert paths, f"{compose_file.name} has no env_file paths"
        for path in paths:
            assert (DOCKER_DIR / path).resolve() == REPO_ROOT / ".env", (
                f"{compose_file.name}: env_file {path} is not the root .env"
            )


def test_justfile_uses_infra_compose_with_pinned_project_name() -> None:
    justfile = (REPO_ROOT / "justfile").read_text()
    assert "-f infra/docker/docker-compose.yml" in justfile
    assert "-p " in justfile, (
        "pin the project name, or it defaults to 'docker' and orphans volumes"
    )
    bare_calls = [
        line.strip()
        for line in justfile.splitlines()
        if "docker compose" in line
        and not line.lstrip().startswith(("#", "compose :="))
    ]
    assert not bare_calls, (
        f"use {{{{ compose }}}} instead of bare docker compose: {bare_calls}"
    )


# --- docker compose config checks ---


@requires_docker
@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.name)
def test_build_contexts_and_dockerfiles_exist(compose_file: Path) -> None:
    services = _compose_config(compose_file)["services"]
    built = {name: svc["build"] for name, svc in services.items() if "build" in svc}
    assert built, f"{compose_file.name} builds no images"
    for name, build in built.items():
        context = Path(build["context"])
        assert context.is_dir(), f"{name}: build context {context} missing"
        dockerfile = (context / build.get("dockerfile", "Dockerfile")).resolve()
        assert dockerfile.is_file(), f"{name}: dockerfile {dockerfile} missing"
        assert dockerfile.parent == DOCKER_DIR, (
            f"{name}: dockerfile must live in infra/docker/"
        )


@requires_docker
@pytest.mark.parametrize("compose_file", COMPOSE_FILES, ids=lambda p: p.name)
def test_bind_mount_sources_exist(compose_file: Path) -> None:
    services = _compose_config(compose_file)["services"]
    for name, svc in services.items():
        for volume in svc.get("volumes", []):
            if volume["type"] == "bind":
                assert Path(volume["source"]).exists(), (
                    f"{name}: bind source {volume['source']} missing"
                )


@requires_docker
def test_dev_host_ports_match_docs() -> None:
    services = _compose_config(DEV_COMPOSE)["services"]
    published = {
        name: svc["ports"][0]["published"]
        for name, svc in services.items()
        if svc.get("ports")
    }
    assert published == DEV_HOST_PORTS
