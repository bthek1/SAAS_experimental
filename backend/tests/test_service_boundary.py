"""The import boundary between `catalog` and `questionnaires` (#13).

Tests, factories and conftest files are exempt: they sit outside the runtime
dependency the split has to break.
"""

import ast
from pathlib import Path

import pytest

APPS = Path(__file__).resolve().parent.parent / "apps"
PORT = "catalog_port.py"


def imported_modules(source: str, package: str) -> set[str]:
    """Absolute dotted names of everything `source` imports, from `package`."""
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parents = package.split(".")[: -(node.level - 1) or None]
                base = ".".join([*parents, base]) if base else ".".join(parents)
            modules.add(base)
            modules.update(f"{base}.{alias.name}" for alias in node.names)
    return modules


def imports_app(source: str, package: str, app: str) -> bool:
    target = f"apps.{app}"
    return any(
        module == target or module.startswith(f"{target}.")
        for module in imported_modules(source, package)
    )


def runtime_modules(app: str):
    for path in sorted((APPS / app).rglob("*.py")):
        name = path.name
        if name.startswith("test_") or name in {"factories.py", "conftest.py"}:
            continue
        if "migrations" in path.parts:
            continue
        package = ".".join(path.relative_to(APPS.parent).parent.parts)
        yield path, package


def violations(importer: str, imported: str, allowed: frozenset[str] = frozenset()):
    return [
        str(path.relative_to(APPS.parent))
        for path, package in runtime_modules(importer)
        if path.name not in allowed and imports_app(path.read_text(), package, imported)
    ]


def test_instances_reach_catalog_only_through_the_port():
    assert violations("questionnaires", "catalog", frozenset({PORT})) == []


def test_catalog_never_imports_instances():
    assert violations("catalog", "questionnaires") == []


@pytest.mark.parametrize(
    ("source", "package"),
    [
        ("from apps.catalog.models import QuestionnaireType", "apps.questionnaires"),
        ("import apps.catalog.models", "apps.questionnaires"),
        ("from apps import catalog", "apps.questionnaires"),
        ("from ..catalog import models", "apps.questionnaires"),
    ],
)
def test_the_check_catches_a_forbidden_import(source, package):
    assert imports_app(source, package, "catalog")


def test_the_check_allows_unrelated_imports():
    source = (
        "from .catalog_port import BatteryType\nfrom apps.utils.cache import cached"
    )
    assert not imports_app(source, "apps.questionnaires", "catalog")
