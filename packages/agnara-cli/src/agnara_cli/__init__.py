"""Project introspection and scaffolding CLI for Agnara.

Owns ``agnara project create``, ``agnara app create``, capability
generation, introspection commands and diagnostics. Templates live here,
never in ``agnara-core``.

Currently implemented: ``agnara inspect``, which imports a compiled
application and presents its filtered protocol-neutral introspection
snapshot as text or as deterministic JSON, ``agnara graph``, which draws the
relationships in that same snapshot, ``agnara schema openapi``, which exports
the OpenAPI document a composition already produced, and ``agnara context``,
which writes the visible capabilities as Markdown for a model to read.
Scaffolding remains ahead in EPIC 0A.

Depends on ``agnara-core``. Must not import a sibling adapter.
See ``ARCHITECTURE.md`` section 15, ``docs/CLI_SPEC.md`` and EPIC 0A.
"""

from ._main import EXIT_FAILED, EXIT_OK, EXIT_USAGE, main
from ._target import ResolvedTarget, TargetError, resolve_attribute, resolve_target

__all__ = [
    "EXIT_FAILED",
    "EXIT_OK",
    "EXIT_USAGE",
    "ResolvedTarget",
    "TargetError",
    "main",
    "resolve_attribute",
    "resolve_target",
]
