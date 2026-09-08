"""Inbound adapter templates, one per exposure selected with ``--with``.

`docs/SCAFFOLDING.md` says ``adapters/inbound/`` starts as a documented, empty
package and that "only the requested inbound adapters are added". This module
is what gets added.

A generated adapter imports **only this app's application layer**. It does not
import ``agnara_http``, ``agnara_mcp`` or any other transport package, for
three reasons that all point the same way:

* No adapter distribution is published to PyPI, and a generated project
  declares ``dependencies = ["agnara"]``. An import of an unpublished package
  would produce a project that cannot be installed.
* ``agnara-http``, ``agnara-a2a`` and ``agnara-events`` declare an empty public
  surface on purpose -- the HTTP composition API is still the golden-design
  sketch in ``docs/API_DESIGN.md`` section 4. Importing them would mean
  importing private names into generated user code.
* It makes `docs/SCAFFOLDING.md`'s invariant -- "No MCP import appears outside
  the MCP adapter file/package" -- true by construction rather than by
  convention.

So each file names the capabilities it projects and records how the projection
is wired, and the developer adds the transport dependency when they choose one.
That is a real seam, not a placeholder: ``EXPOSED`` is the list an adapter
iterates, and it is what keeps "which capabilities does this protocol serve?"
answerable in one place.

See ADR 0063.
"""

from __future__ import annotations

__all__ = ["inbound_adapter"]

#: Exposure -> (what this protocol projects a capability *as*, the wiring note).
#: Taken from the `adapters/inbound/` examples in `docs/SCAFFOLDING.md`.
_KINDS: dict[str, tuple[str, str]] = {
    "http": (
        "HTTP routes",
        "Bind each capability to a method and path, and let the adapter\n"
        "project the OpenAPI document from the same declarations.",
    ),
    "mcp": (
        "MCP tools",
        "Project each capability as a tool. Its input schema is the one the\n"
        "runtime already compiled, so the tool contract is not written twice.",
    ),
    "a2a": (
        "A2A skills",
        "Project each capability as a skill on this app's Agent Card.",
    ),
    "tasks": (
        "background executions",
        "Submit an invocation and report progress against it, rather than\n"
        "answering inside the caller's request.",
    ),
    "events": (
        "event consumers",
        "Map an inbound message to an invocation, and decide there what an\n"
        "unprocessable message does.",
    ),
}

#: The exposures this module can generate an adapter for.
EXPOSURE_SUMMARY = tuple(sorted(_KINDS))


def inbound_adapter(app: str, exposure: str) -> str:
    """The ``adapters/inbound/<exposure>.py`` module for one exposure.

    Args:
        app: the app name, used in the generated documentation.
        exposure: one of `EXPOSURE_SUMMARY`.

    Returns:
        The module source, with ``{module}`` left for the caller to substitute.

    Raises:
        KeyError: `exposure` has no template.
    """
    projects_as, wiring = _KINDS[exposure]
    return f'''"""{exposure} projection into the {app} app's capabilities.

An inbound adapter maps protocol-specific data to a capability invocation. It
is the only place in this app that may know about {exposure}: nothing in
``domain/`` or ``application/`` imports a transport, which is what lets the
same capabilities be reached from every protocol.

This module projects the capabilities below as {projects_as}.

{wiring}

Nothing here imports an Agnara adapter distribution yet. Add the one you want
to this project's dependencies, then wire it against ``EXPOSED`` -- the
capabilities stay exactly as they are, because the projection happens here and
not in the application layer.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ...application.capabilities import get_record, list_records

__all__ = ["EXPOSED"]

#: The capabilities this adapter projects, in the order it should present
#: them. Keeping the list here means "which capabilities does {exposure}
#: serve?" has one answer, and adding a capability to this protocol is a
#: one-line change in the layer that owns the protocol.
EXPOSED: tuple[Callable[..., Any], ...] = (get_record, list_records)
'''
