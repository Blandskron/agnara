"""E1A.5: generated projects enforce explicit contracts between apps."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

from agnara_cli import EXIT_OK, main

PROJECT = "shop"
PROBE = Path("src/shop/apps/payments/application/cross_app.py")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    assert main(["project", "create", PROJECT, "--directory", str(tmp_path)]) == EXIT_OK
    root = tmp_path / PROJECT
    for app in ("payments", "catalog"):
        assert main(["app", "create", app, "--project", str(root)]) == EXIT_OK
    return root


def _architecture_test(project: Path) -> ModuleType:
    location = project / "tests" / "test_architecture.py"
    spec = importlib.util.spec_from_file_location("generated_architecture_tests", location)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "source",
    [
        "from shop.apps.catalog.application.contracts import RecordView\n",
        "from ...catalog.application.contracts import RecordView\n",
    ],
)
def test_an_app_may_import_another_app_s_public_contract(project: Path, source: str) -> None:
    (project / PROBE).write_text(source, encoding="utf-8", newline="\n")

    _architecture_test(project).test_apps_import_only_public_contracts()


@pytest.mark.parametrize(
    "module",
    [
        "domain.models",
        "application.capabilities",
        "application.contracts.internal",
        "application.ports",
        "application.services",
        "adapters.outbound.memory",
        "module",
        "tests.test_capabilities",
    ],
)
def test_an_app_may_not_import_another_app_s_internals(project: Path, module: str) -> None:
    imported = f"shop.apps.catalog.{module}"
    (project / PROBE).write_text(f"import {imported}\n", encoding="utf-8", newline="\n")

    with pytest.raises(AssertionError, match=re.escape(imported)):
        _architecture_test(project).test_apps_import_only_public_contracts()


def test_a_relative_import_cannot_bypass_the_boundary(project: Path) -> None:
    source = "from ...catalog.adapters.outbound.memory import InMemoryRecordRepository\n"
    (project / PROBE).write_text(source, encoding="utf-8", newline="\n")

    with pytest.raises(AssertionError, match=r"catalog\.adapters\.outbound\.memory"):
        _architecture_test(project).test_apps_import_only_public_contracts()
