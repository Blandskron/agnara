"""Agnara — a capability-first, transport-neutral execution kernel.

``agnara-core`` owns the semantics shared by every transport: the capability
model, the registry, execution context, the dependency graph, policies,
execution planning and canonical errors.

It must never import a protocol implementation, a server, a schema library
or an LLM SDK. See ``ARCHITECTURE.md`` section 3 and ``PRINCIPLES.md`` P2.

Currently implemented: the capability declaration model (EPIC 1). The
registry, decorator, execution plans and policies are still ahead in
``BACKLOG.md``.
"""

from importlib.metadata import version

from agnara.capability import (
    CapabilityDefinition,
    CapabilityId,
    Confirmation,
    Idempotency,
    Risk,
    StandardEffect,
)
from agnara.errors import AgnaraError, DefinitionError

__version__ = version("agnara-core")

__all__ = [
    "AgnaraError",
    "CapabilityDefinition",
    "CapabilityId",
    "Confirmation",
    "DefinitionError",
    "Idempotency",
    "Risk",
    "StandardEffect",
    "__version__",
]
