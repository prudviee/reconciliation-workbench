from __future__ import annotations

import ast
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_ROOT = PROJECT_ROOT / "reconciliation" / "domain"
FORBIDDEN_DOMAIN_IMPORTS = {
    "books",
    "config",
    "django",
    "foundation",
    "observability",
    "psycopg",
    "workspaces",
}


def imported_root_names(source: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.partition(".")[0])
    return roots


def test_domain_source_has_no_framework_or_adapter_imports() -> None:
    violations: dict[str, list[str]] = {}
    for source_file in DOMAIN_ROOT.rglob("*.py"):
        imports = imported_root_names(source_file.read_text(encoding="utf-8"))
        forbidden = sorted(imports & FORBIDDEN_DOMAIN_IMPORTS)
        if forbidden:
            violations[str(source_file.relative_to(PROJECT_ROOT))] = forbidden

    assert violations == {}


def test_distribution_discovers_every_application_package() -> None:
    configuration = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    includes = set(configuration["tool"]["setuptools"]["packages"]["find"]["include"])

    assert includes == {
        "books*",
        "config*",
        "foundation*",
        "observability*",
        "reconciliation*",
        "workspaces*",
    }


def test_only_web_service_applies_database_migrations() -> None:
    compose = (PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert compose.count("python manage.py migrate --noinput") == 1
