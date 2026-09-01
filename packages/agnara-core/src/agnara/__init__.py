"""Agnara — a capability-first, transport-neutral execution kernel.

``agnara-core`` owns the semantics shared by every transport: the capability
model, the registry, execution context, the dependency graph, policies,
execution planning and canonical errors.

It must never import a protocol implementation, a server, a schema library
or an LLM SDK. See ``ARCHITECTURE.md`` section 3 and ``PRINCIPLES.md`` P2.

Currently implemented: the capability declaration model and the registry
(EPIC 1). The decorator, execution plans and policies are still ahead in
``BACKLOG.md``.
"""

from importlib.metadata import version

from agnara.capability import (
    CapabilityDefinition,
    CapabilityId,
    CapabilityRegistry,
    Confirmation,
    FrozenCapabilityRegistry,
    Idempotency,
    Risk,
    StandardEffect,
)
from agnara.errors import (
    AgnaraError,
    DefinitionError,
    DuplicateCapabilityError,
    RegistryError,
    RegistryFrozenError,
    UnknownCapabilityError,
)

__version__ = version("agnara-core")

__all__ = [
    "AgnaraError",
    "CapabilityDefinition",
    "CapabilityId",
    "CapabilityRegistry",
    "Confirmation",
    "DefinitionError",
    "DuplicateCapabilityError",
    "FrozenCapabilityRegistry",
    "Idempotency",
    "RegistryError",
    "RegistryFrozenError",
    "Risk",
    "StandardEffect",
    "UnknownCapabilityError",
    "__version__",
]
