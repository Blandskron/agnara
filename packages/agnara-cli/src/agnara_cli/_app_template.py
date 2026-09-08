"""The default ``modular-hexagonal`` app template.

`docs/SCAFFOLDING.md` specifies the layout and says the generator "must NOT
generate dozens of meaningless empty files". So the generated app is a working
example rather than a skeleton: a domain, an application port, two capabilities
that depend on that port, an outbound adapter that implements it, and tests
that pass. A reader can see why the layers are separated instead of being told.

The example is deliberately domain-neutral. An app may be called ``payments``,
``catalog`` or ``users``, and a generator that invented banking concepts for a
catalog would produce code its first reader has to delete. What it does show is
the direction of every dependency: application depends on its port, the adapter
implements the port, and neither the domain nor the application imports a
transport.

Every template is a pure function of the project and app names, so two runs
with the same inputs produce byte-identical output. See ADR 0061.
"""

from __future__ import annotations

from agnara_cli._exposure_template import inbound_adapter
from agnara_cli._template_format import format_python_template

__all__ = ["app_files"]


def _class_prefix(app: str) -> str:
    """``payment_methods`` becomes ``PaymentMethods`` for error class names."""
    return "".join(part.title() for part in app.split("_") if part)


def _init(summary: str, detail: str = "") -> str:
    """A package docstring, wrapped so the generated file is Ruff-clean."""
    body = summary if not detail else summary + chr(10) + chr(10) + detail
    return chr(34) * 3 + body + chr(34) * 3 + chr(10) * 2 + "__all__: list[str] = []" + chr(10)


def _app_init(project: str, app: str) -> str:
    return f'''"""The {app} app: one bounded context of the {project} project.

Layers, and the direction they depend in:

    adapters/inbound  -> application -> domain
    adapters/outbound -> application (implements its ports)

Nothing here imports a transport package. ``module.register`` is the only
place that wires this app into a project composition.
"""

__all__: list[str] = []
'''


def _value_objects(app: str) -> str:
    return f'''"""Value objects of the {app} domain.

A value object has no identity of its own: two with the same contents are the
same value. Frozen, so one cannot be changed after it has been validated.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Reference"]


@dataclass(frozen=True, slots=True)
class Reference:
    """A stable identifier for one record in this app.

    Replace this with the identifier your domain actually has. Keeping it a
    value object rather than a bare ``str`` is what lets the type system say
    which strings are references and which are not.
    """

    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("a reference must not be empty")
'''


def _models(app: str) -> str:
    return f'''"""Entities of the {app} domain.

Pure business concepts. No framework import, no transport type, no storage
concern: this module should still make sense if every adapter were replaced.
"""

from __future__ import annotations

from dataclasses import dataclass

from .value_objects import Reference

__all__ = ["Record"]


@dataclass(frozen=True, slots=True)
class Record:
    """One thing this app is responsible for.

    Rename it to whatever your domain calls its central concept, and give it
    the invariants that concept actually has.
    """

    reference: Reference
    label: str
'''


def _errors(app: str) -> str:
    prefix = _class_prefix(app)
    return f'''"""Errors of the {app} domain.

Domain errors are protocol-neutral. An adapter decides what an HTTP status or
an MCP error looks like; the domain only says what went wrong.
"""

from __future__ import annotations

from .value_objects import Reference

__all__ = ["{prefix}Error", "RecordNotFound"]


class {prefix}Error(Exception):
    """Base class for every error this app raises.

    One base lets a caller distinguish this app's failures from anything else
    without catching bare ``Exception``.
    """


class RecordNotFound({prefix}Error):
    """No record exists for the requested reference."""

    def __init__(self, reference: Reference) -> None:
        super().__init__(f"no record for {{reference.value!r}}")
        self.reference = reference
'''


def _ports(app: str) -> str:
    return f'''"""What the {app} application needs from the outside world.

A port is a protocol the application depends on and an adapter implements.
Declaring it here, rather than importing a repository directly, is what keeps
the direction of the dependency pointing inward: storage can be replaced
without the application knowing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..domain.models import Record
from ..domain.value_objects import Reference

__all__ = ["RecordRepository"]


@runtime_checkable
class RecordRepository(Protocol):
    """Read access to this app's records."""

    def get(self, reference: Reference) -> Record | None:
        """Return the record with this reference, or ``None``."""
        ...

    def all(self) -> tuple[Record, ...]:
        """Return every record, in a stable order."""
        ...
'''


def _capabilities(project: str, app: str) -> str:
    return f'''"""Capabilities of the {app} app.

A capability is the unit of behaviour. It is declared once, here, and exposed
over any transport by an adapter — never the other way round. These functions
know nothing about HTTP, MCP or any protocol, and that is the point.

A parameter annotated with a registered dependency type is supplied by the
runtime, not by the caller: ``records`` never appears in a capability's input
schema and a caller cannot pass one.
"""

from __future__ import annotations

from ..domain.errors import RecordNotFound
from ..domain.value_objects import Reference
from .contracts import RecordView
from .ports import RecordRepository

__all__ = ["get_record", "list_records"]


def get_record(reference: str, records: RecordRepository) -> RecordView:
    """Read one record by its reference."""
    identifier = Reference(reference)
    found = records.get(identifier)
    if found is None:
        raise RecordNotFound(identifier)
    return {{"reference": found.reference.value, "label": found.label}}


def list_records(records: RecordRepository) -> list[RecordView]:
    """List every record this app holds."""
    return [
        {{"reference": record.reference.value, "label": record.label}} for record in records.all()
    ]
'''


def _contracts(app: str) -> str:
    return f'''"""Public application contracts offered by the {app} app.

Another app may import types and protocols from this module. Everything else
inside this app remains an implementation detail. A contract describes data
or behaviour; it never imports an adapter and never calls a capability
directly, because an internal call must not bypass runtime policy.
"""

from __future__ import annotations

from typing import TypedDict

__all__ = ["RecordView"]


class RecordView(TypedDict):
    """The stable record shape this app offers to other application code."""

    reference: str
    label: str
'''


def _outbound_memory(app: str) -> str:
    return f'''"""An in-memory implementation of the {app} record port.

Enough to run and to test against. Replace it with the real storage adapter —
a database, an HTTP client, a queue — and the application layer does not
change, because it depends on the port rather than on this class.
"""

from __future__ import annotations

from collections.abc import Iterable

from ...domain.models import Record
from ...domain.value_objects import Reference

__all__ = ["InMemoryRecordRepository"]


class InMemoryRecordRepository:
    """Holds records in a dictionary keyed by reference."""

    __slots__ = ("_records",)

    def __init__(self, records: Iterable[Record] = ()) -> None:
        self._records: dict[Reference, Record] = {{record.reference: record for record in records}}

    def get(self, reference: Reference) -> Record | None:
        """Return the record with this reference, or ``None``."""
        return self._records.get(reference)

    def all(self) -> tuple[Record, ...]:
        """Return every record, in insertion order."""
        return tuple(self._records.values())
'''


def _module(project: str, app: str) -> str:
    return f'''"""Wire the {app} app into a project composition.

This is the only module that knows about both the application and its
adapters. Keep it small: it registers, it does not implement.

Call it from the project composition root::

    from {project}.apps.{app} import module as {app}_module

    {app}_module.register(app, dependencies)
"""

from __future__ import annotations

from agnara import Agnara, App
from agnara.core.di import DIRegistry, provider

from .adapters.outbound.memory import InMemoryRecordRepository
from .application.capabilities import get_record, list_records
from .application.ports import RecordRepository
from .domain.models import Record
from .domain.value_objects import Reference

__all__ = ["{app}", "provide_records", "register"]


@provider()
def provide_records() -> RecordRepository:
    """Build this app's record repository.

    Replace the in-memory adapter with the real one here. Nothing in the
    application layer changes when you do.
    """
    return InMemoryRecordRepository([Record(Reference("example-1"), "first example record")])


#: This bounded context, and the capabilities it owns. Declared at import
#: time, so importing this module is enough to inspect or test the app on its
#: own -- no project required. The name becomes the capability namespace, so
#: these are ``{app}.get_record`` and ``{app}.list_records`` whichever project
#: mounts them.
{app} = App(
    "{app}",
    description="The {app} bounded context.",
    module="{{module}}",
)

{app}.capability(
    description="Read one {app} record.",
    idempotent=True,
)(get_record)
{app}.capability(
    description="List every {app} record.",
    idempotent=True,
)(list_records)


def register(app: Agnara, dependencies: DIRegistry) -> None:
    """Bind this app's providers and mount it on a composition.

    Registration closes when the project calls ``compile()``, so this must run
    at import time of the composition root, not later.
    """
    dependencies.bind(RecordRepository, provide_records)
    app.include({app})
'''


def _tests(app: str) -> str:
    return f'''"""The {app} capabilities work against the port, not against storage.

These tests construct the adapter directly and call the capabilities as
functions. No application, no transport and no dependency injection is needed
to prove the behaviour, which is what the layering buys.
"""

from __future__ import annotations

import pytest

from ..adapters.outbound.memory import InMemoryRecordRepository
from ..application.capabilities import get_record, list_records
from ..domain.errors import RecordNotFound
from ..domain.models import Record
from ..domain.value_objects import Reference


def repository() -> InMemoryRecordRepository:
    return InMemoryRecordRepository(
        [
            Record(Reference("r-1"), "first"),
            Record(Reference("r-2"), "second"),
        ]
    )


def test_get_record_returns_the_stored_record() -> None:
    assert get_record("r-1", repository()) == {{"reference": "r-1", "label": "first"}}


def test_get_record_rejects_an_unknown_reference() -> None:
    with pytest.raises(RecordNotFound):
        get_record("missing", repository())


def test_list_records_returns_every_record_in_order() -> None:
    assert [record["reference"] for record in list_records(repository())] == ["r-1", "r-2"]


def test_a_reference_may_not_be_empty() -> None:
    """The value object holds the invariant, so no caller has to remember it."""
    with pytest.raises(ValueError, match="must not be empty"):
        Reference("   ")


def test_an_empty_repository_lists_nothing() -> None:
    assert list_records(InMemoryRecordRepository()) == []
'''


def app_files(project: str, app: str, exposures: tuple[str, ...] = ()) -> dict[str, str]:
    """Every file ``agnara app create`` writes, keyed by project-relative path.

    Templates refer to the app's own package as ``{module}`` so the import
    paths are written once here rather than in every template string.

    ``exposures`` adds one ``adapters/inbound/<exposure>.py`` each, which is
    all `docs/SCAFFOLDING.md` asks ``--with`` to add.
    """
    module = f"{project}.apps.{app}"
    root = f"src/{project}/apps/{app}"
    files = {
        f"{root}/__init__.py": _app_init(project, app),
        f"{root}/module.py": _module(project, app),
        f"{root}/domain/__init__.py": _init(f"Pure business concepts of the {app} app."),
        f"{root}/domain/models.py": _models(app),
        f"{root}/domain/value_objects.py": _value_objects(app),
        f"{root}/domain/errors.py": _errors(app),
        f"{root}/application/__init__.py": _init(
            f"Use cases of the {app} app, and the ports they depend on."
        ),
        f"{root}/application/capabilities.py": _capabilities(project, app),
        f"{root}/application/contracts.py": _contracts(app),
        f"{root}/application/ports.py": _ports(app),
        f"{root}/adapters/__init__.py": _init(
            f"Protocol and infrastructure adapters of the {app} app."
        ),
        f"{root}/adapters/inbound/__init__.py": _init(
            f"Inbound adapters of the {app} app.",
            "A protocol projection into this app's capabilities: an HTTP route,\n"
            "an MCP tool, an event consumer. Nothing outside this package should\n"
            "import a transport.",
        ),
        f"{root}/adapters/outbound/__init__.py": _init(
            f"Outbound adapters of the {app} app.",
            "Implementations of this app's application ports: a repository, a\n"
            "client, a publisher. An app may have none.",
        ),
        f"{root}/adapters/outbound/memory.py": _outbound_memory(app),
        f"{root}/tests/__init__.py": _init(f"Tests local to the {app} app."),
        f"{root}/tests/test_capabilities.py": _tests(app),
    }
    for exposure in exposures:
        files[f"{root}/adapters/inbound/{exposure}.py"] = inbound_adapter(app, exposure)
    return {
        path: format_python_template(contents.replace("{module}", module))
        for path, contents in files.items()
    }
