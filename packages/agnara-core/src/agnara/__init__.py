"""Agnara — a capability-first, transport-neutral execution kernel.

``agnara-core`` owns the semantics shared by every transport: the capability
model, the registry, execution context, the dependency graph, policies,
execution planning and canonical errors.

It must never import a protocol implementation, a server, a schema library
or an LLM SDK. See ``ARCHITECTURE.md`` section 3 and ``PRINCIPLES.md`` P2.

The public capability API is defined by EPIC 1 in ``BACKLOG.md`` and is not
implemented yet.
"""

from importlib.metadata import version

__version__ = version("agnara-core")

__all__ = ["__version__"]
