"""The ``minimal`` app template.

``docs/CLI_SPEC.md`` describes this architecture as being "for very small
capabilities, experiments and examples", and ADR 0012 records it as the escape
hatch from the modular-hexagonal default. ``docs/SCAFFOLDING.md`` fixes the
layout: a package, ``module.py``, ``capabilities.py`` and a test.

It deliberately declares the same two capabilities as the default template,
over the same vocabulary, and holds their data in the module instead of behind
a port. Someone comparing the two templates is then reading one difference --
where the data comes from -- rather than two unrelated examples, which is the
question `--architecture` actually asks them to decide.

A minimal app is still a real app: it registers through the same
``module.register(app, dependencies)`` contract, so moving to
``modular-hexagonal`` later changes the app's internals and not the
composition root.

Every template is a pure function of the project and app names, so two runs
with the same inputs produce byte-identical output. See ADR 0061.
"""

from __future__ import annotations

__all__ = ["minimal_app_files"]


def _app_init(project: str, app: str) -> str:
    return f'''"""The {app} app: one bounded context of the {project} project.

A minimal app keeps its capabilities in one module. There is no domain,
application or adapters package, because at this size the separation would
cost more than it explains.

Reach for ``modular-hexagonal`` when this app grows a reason to name its
layers: data that comes from somewhere else, a rule worth isolating from the
thing that stores it, or a second implementation of the same port.

Nothing here imports a transport. ``module.register`` is the only place that
wires this app into a project composition.
"""

__all__: list[str] = []
'''


def _capabilities(app: str) -> str:
    return f'''"""Capabilities of the {app} app.

A capability is the unit of behaviour. It is declared once, here, and exposed
over any transport by an adapter -- never the other way round. These functions
know nothing about HTTP, MCP or any protocol, and that is the point.

The records live in this module. That is the whole difference between this
template and ``modular-hexagonal``: there, the same two capabilities depend on
a port and an adapter supplies it. Introduce that separation when the data
stops being a constant, and these signatures barely change.
"""

from __future__ import annotations

from typing import Final

__all__ = ["RecordNotFound", "get_record", "list_records"]

#: The records this app knows about, in the order they are listed.
_RECORDS: Final[tuple[tuple[str, str], ...]] = (
    ("example-1", "first example record"),
    ("example-2", "second example record"),
)


class RecordNotFound(LookupError):
    """No record in this app carries the requested reference.

    A distinct type rather than a bare ``LookupError``: an adapter maps this
    to a 404 or an MCP error, and it cannot do that for a generic exception
    raised somewhere further down.
    """

    def __init__(self, reference: str) -> None:
        super().__init__(f"no {app} record with reference {{reference!r}}")
        self.reference = reference


def get_record(reference: str) -> dict[str, str]:
    """Read one record by its reference.

    Raises:
        RecordNotFound: no record carries this reference.
    """
    for stored, label in _RECORDS:
        if stored == reference:
            return {{"reference": stored, "label": label}}
    raise RecordNotFound(reference)


def list_records() -> list[dict[str, str]]:
    """List every record this app holds, in declaration order."""
    return [{{"reference": reference, "label": label}} for reference, label in _RECORDS]
'''


def _module(project: str, app: str) -> str:
    return f'''"""Wire the {app} app into a project composition.

This is the only module that knows how this app attaches to a project. Keep it
small: it registers, it does not implement.

Call it from the project composition root::

    from {project}.apps.{app} import module as {app}_module

    {app}_module.register(app, dependencies)
"""

from __future__ import annotations

from agnara import Agnara
from agnara.core.di import DIRegistry

from {{module}}.capabilities import get_record, list_records

__all__ = ["register"]


def register(app: Agnara, dependencies: DIRegistry) -> None:
    """Register this app's capabilities on a composition.

    ``dependencies`` is unused: a minimal app declares no providers, because
    its capabilities take everything they need as arguments. The parameter
    stays so that every app registers the same way, and so that adding a
    provider here later is not a change the composition root has to notice.

    Registration closes when the project calls ``compile()``, so this must run
    at import time of the composition root, not later.
    """
    app.capability(description="Read one {app} record.", idempotent=True)(get_record)
    app.capability(description="List every {app} record.", idempotent=True)(list_records)
'''


def _tests(app: str) -> str:
    return f'''"""The {app} capabilities are plain functions, so the tests are plain too.

No application, no transport and no dependency injection is needed to prove
the behaviour of a minimal app -- which is the reason to start here.
"""

from __future__ import annotations

import pytest

from {{module}}.capabilities import RecordNotFound, get_record, list_records


def test_get_record_returns_the_stored_record() -> None:
    assert get_record("example-1") == {{"reference": "example-1", "label": "first example record"}}


def test_get_record_rejects_an_unknown_reference() -> None:
    with pytest.raises(RecordNotFound):
        get_record("missing")


def test_the_failure_carries_the_reference_that_was_asked_for() -> None:
    """An adapter reports what was not found, so it must not be lost."""
    with pytest.raises(RecordNotFound) as raised:
        get_record("missing")
    assert raised.value.reference == "missing"


def test_list_records_returns_every_record_in_declaration_order() -> None:
    assert [record["reference"] for record in list_records()] == ["example-1", "example-2"]


def test_listing_does_not_expose_the_module_state() -> None:
    """A caller that mutates the result must not change what the app holds."""
    listed = list_records()
    listed.clear()
    assert len(list_records()) == 2
'''


def _tests_init(app: str) -> str:
    return f'''"""Tests local to the {app} app."""

__all__: list[str] = []
'''


def minimal_app_files(project: str, app: str) -> dict[str, str]:
    """Every file ``agnara app create --architecture minimal`` writes.

    Keyed by project-relative path. Templates refer to the app's own package as
    ``{module}`` so the import paths are written once here rather than in every
    template string.
    """
    module = f"{project}.apps.{app}"
    root = f"src/{project}/apps/{app}"
    files = {
        f"{root}/__init__.py": _app_init(project, app),
        f"{root}/module.py": _module(project, app),
        f"{root}/capabilities.py": _capabilities(app),
        f"{root}/tests/__init__.py": _tests_init(app),
        f"{root}/tests/test_capabilities.py": _tests(app),
    }
    return {path: contents.replace("{module}", module) for path, contents in files.items()}
