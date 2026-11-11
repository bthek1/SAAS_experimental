"""The boundaries between the services and `common` (#13)."""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
CATALOG = BACKEND / "catalog"
INSTANCES = BACKEND / "instances"
COMMON = BACKEND / "common" / "common"

CATALOG_ONLY = ("apps.catalog", "apps.accounts", "apps.utils")
INSTANCES_ONLY = ("apps.questionnaires",)


def imported_modules(source: str) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level:
            base = node.module or ""
            modules.add(base)
            modules.update(f"{base}.{alias.name}" for alias in node.names)
    return modules


def imports_any(source: str, targets: tuple[str, ...]) -> bool:
    return any(
        module == target or module.startswith(f"{target}.")
        for module in imported_modules(source)
        for target in targets
    )


def python_files(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if "migrations" not in path.parts and ".venv" not in path.parts
    ]


def offenders(root: Path, targets: tuple[str, ...]) -> list[str]:
    return [
        str(path.relative_to(BACKEND))
        for path in python_files(root)
        if imports_any(path.read_text(), targets)
    ]


def test_no_import_between_services():
    # Tests too: the two `apps` packages never exist in one process.
    assert offenders(INSTANCES, CATALOG_ONLY) == []
    assert offenders(CATALOG, INSTANCES_ONLY) == []


def test_common_imports_no_service():
    assert offenders(COMMON, ("apps", "core", *CATALOG_ONLY, *INSTANCES_ONLY)) == []


def test_parity_suite_imports_no_service_code():
    # It tests catalog over HTTP only, so it can test any implementation (#34).
    # The dev keypair is the one shared module it may read.
    targets = ("django", "rest_framework", "apps", "core", "catalog_fastapi")
    assert offenders(BACKEND / "parity", targets) == []
    common = {
        module
        for path in python_files(BACKEND / "parity")
        for module in imported_modules(path.read_text())
        if module.startswith("common")
    }
    assert common <= {"common.dev_keys", "common.dev_keys.DEV_VERIFYING_KEY"}


def test_catalog_fastapi_imports_no_django():
    # It replaces Django's catalog (#35). Of `common`, which is Django-based, it
    # reads only the shared dev keypair and gunicorn rules.
    package = BACKEND / "catalog_fastapi"
    targets = ("django", "rest_framework", "apps", "core")
    assert offenders(package, targets) == []
    common = {
        module
        for path in python_files(package)
        for module in imported_modules(path.read_text())
        if module == "common" or module.startswith("common.")
    }
    allowed = ("common.dev_keys", "common.gunicorn_conf")
    assert all(module.startswith(allowed) for module in common), common


def test_no_service_imports_catalog_fastapi():
    for root in (CATALOG, INSTANCES, COMMON):
        assert offenders(root, ("catalog_fastapi",)) == []


def test_common_has_no_models():
    assert not (COMMON / "models.py").exists()
    for path in python_files(COMMON):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ClassDef):
                bases = [ast.unparse(base) for base in node.bases]
                assert "models.Model" not in bases, f"{path}: {node.name}"


def test_instances_never_call_get_user_model():
    found = []
    for path in python_files(INSTANCES):
        source = path.read_text()
        if "get_user_model" in source or "AUTH_USER_MODEL" in source:
            found.append(str(path.relative_to(BACKEND)))
    assert found == []


@pytest.mark.parametrize(
    "source",
    [
        "from apps.catalog.models import QuestionnaireType",
        "import apps.catalog.models",
        "from apps import catalog",
    ],
)
def test_the_check_catches_a_forbidden_import(source):
    assert imports_any(source, CATALOG_ONLY)


def test_the_check_allows_unrelated_imports():
    assert not imports_any("from common.cache import cached", CATALOG_ONLY)
