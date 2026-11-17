"""The boundaries between the services and `common` (#13, #45, #51).

catalog is FastAPI (#38). instances runs on .NET (`instances_NET`, #42 to #45), which
shares no code with Python: it reads `backend/contracts/` and, in tests,
`common/dev_keys.py` as files. Its Django version is kept beside it (`instances_Django`,
#51), with the Django infrastructure that left `common` in #45 in its own `shared/`, and
its Go version (`instances_GO`, #52) shares no code with Python either.
"""

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
CATALOG = BACKEND / "catalog"
INSTANCES_NET = BACKEND / "instances_NET"
INSTANCES_DJANGO = BACKEND / "instances_Django"
INSTANCES_GO = BACKEND / "instances_GO"
COMMON = BACKEND / "common" / "common"

CATALOG_ONLY = ("catalog",)
DJANGO = ("django", "rest_framework", "apps", "core", "shared")


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


def test_instances_net_has_no_python():
    found = [str(p.relative_to(BACKEND)) for p in python_files(INSTANCES_NET)]
    assert found == []


def test_instances_go_has_no_python():
    found = [str(p.relative_to(BACKEND)) for p in python_files(INSTANCES_GO)]
    assert found == []


def test_instances_django_imports_no_catalog():
    # Like catalog, it reads only the shared dev keypair and gunicorn rules of `common`.
    assert offenders(INSTANCES_DJANGO, CATALOG_ONLY) == []
    common = {
        module
        for path in python_files(INSTANCES_DJANGO)
        for module in imported_modules(path.read_text())
        if module == "common" or module.startswith("common.")
    }
    allowed = ("common.dev_keys", "common.gunicorn_conf")
    assert common, "expected instances_Django to read the dev keypair"
    assert all(module.startswith(allowed) for module in common), common


def test_common_imports_no_service():
    assert offenders(COMMON, (*CATALOG_ONLY, *DJANGO)) == []


def test_common_holds_only_what_catalog_and_the_tests_share():
    # The Django infrastructure left with Django's instances (#45): its `shared/` (#51).
    modules = {p.stem for p in python_files(COMMON)}
    assert modules == {"__init__", "dev_keys", "gunicorn_conf"}


def test_parity_suite_imports_no_service_code():
    # It tests catalog over HTTP only, which let it check two implementations (#34).
    # The dev keypair is the one shared module it may read.
    assert offenders(BACKEND / "parity", (*DJANGO, *CATALOG_ONLY)) == []
    common = {
        module
        for path in python_files(BACKEND / "parity")
        for module in imported_modules(path.read_text())
        if module.startswith("common")
    }
    assert common <= {"common.dev_keys", "common.dev_keys.DEV_VERIFYING_KEY"}


def test_instances_parity_suite_imports_no_service_code():
    # It tests instances over HTTP only, which let it check Django and .NET (#40, #42).
    assert offenders(BACKEND / "parity_instances", (*DJANGO, *CATALOG_ONLY)) == []
    common = {
        module
        for path in python_files(BACKEND / "parity_instances")
        for module in imported_modules(path.read_text())
        if module.startswith("common")
    }
    assert common <= {"common.dev_keys", "common.dev_keys.DEV_SIGNING_KEY"}


def test_no_python_package_reaches_into_instances():
    # Only the test harnesses that start it (parity_instances, tests/) know where it
    # lives or what it is called. Neither implementation knows of the other.
    found = [
        str(path.relative_to(BACKEND))
        for root in (CATALOG, BACKEND / "common", INSTANCES_DJANGO)
        for path in python_files(root)
        if any(
            marker in path.read_text()
            for marker in (
                "Instances.Api",
                "instances_NET",
                "instances_Django",
                "instances_GO",
            )
        )
    ]
    assert found == []


def test_catalog_imports_no_django():
    # FastAPI, on the tables Django made (#35 to #38). Of `common` it reads only the
    # shared dev keypair and gunicorn rules.
    assert offenders(CATALOG, DJANGO) == []
    common = {
        module
        for path in python_files(CATALOG)
        for module in imported_modules(path.read_text())
        if module == "common" or module.startswith("common.")
    }
    allowed = ("common.dev_keys", "common.gunicorn_conf")
    assert all(module.startswith(allowed) for module in common), common


@pytest.mark.parametrize(
    "source",
    [
        "from catalog.models import QuestionnaireType",
        "import catalog.models",
        "from catalog import services",
    ],
)
def test_the_check_catches_a_forbidden_import(source):
    assert imports_any(source, CATALOG_ONLY)


def test_the_check_allows_unrelated_imports():
    assert not imports_any("from common.dev_keys import DEV_SIGNING_KEY", CATALOG_ONLY)
