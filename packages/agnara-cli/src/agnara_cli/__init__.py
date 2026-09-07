"""Project introspection and scaffolding CLI for Agnara.

Owns ``agnara project create``, ``agnara app create``, capability
generation, introspection commands and diagnostics. Templates live here,
never in ``agnara-core``.

Currently implemented: ``agnara project create`` and ``agnara app create``,
which generate a project and a bounded context from a reviewable plan,
``agnara apps``, which lists what ``agnara.toml`` declares without importing
anything, ``agnara inspect``, which imports a compiled
application and presents its filtered protocol-neutral introspection
snapshot as text or as deterministic JSON, ``agnara graph``, which draws the
relationships in that same snapshot, ``agnara schema openapi``, which exports
the OpenAPI document a composition already produced, and ``agnara context``,
which writes the visible capabilities as Markdown for a model to read. Exposure
selection and capability generation remain ahead in EPIC 0A.

Depends on ``agnara-core``. Must not import a sibling adapter.
See ``ARCHITECTURE.md`` section 15, ``docs/CLI_SPEC.md`` and EPIC 0A.
"""

#: The supported programmatic surface of this distribution.
#:
#: ``agnara-cli`` is consumed as the ``agnara`` command. The four names below
#: are what a caller needs to run that command in-process — a test harness, a
#: task runner, a wrapper script — and nothing else is a contract. Manifest
#: parsing, generation planning and target resolution are how the commands are
#: implemented; they were re-exported from underscore-prefixed modules without
#: ever being documented, used or designed as an API (ADR 0076).
from ._main import EXIT_FAILED, EXIT_OK, EXIT_USAGE, main

__all__ = [
    "EXIT_FAILED",
    "EXIT_OK",
    "EXIT_USAGE",
    "main",
]
