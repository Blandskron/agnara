"""Agnara ???????? a capability-first, transport-neutral execution kernel.

``agnara-core`` owns the semantics shared by every transport: the capability
model, the registry, execution context, the dependency graph, policies,
execution planning and canonical errors.

It must never import a protocol implementation, a server, a schema library
or an LLM SDK. See ``ARCHITECTURE.md`` section 3 and ``PRINCIPLES.md`` P2.

Currently implemented: capability declaration and registration, schema ports,
dependency compilation/resolution, execution plans, and direct invocation.
Policies and transport adapters remain ahead in ``BACKLOG.md``.
"""

from importlib.metadata import version

from agnara.application import Agnara
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
    InvocationError,
    RegistryError,
    RegistryFrozenError,
    SchemaError,
    UnknownCapabilityError,
    ValidationError,
)
from agnara.policy.base import Policy, PolicyFailure, PolicyResult, PolicySuccess
from agnara.policy.principal import AnonymousPrincipal, Principal
from agnara.schema import (
    JsonSchema,
    SchemaAdapter,
    StandardSchemaAdapter,
    TypeSchema,
)

__version__ = version("agnara")

__all__ = [
    "Agnara",
    "AgnaraError",
    "AnonymousPrincipal",
    "CapabilityDefinition",
    "CapabilityId",
    "CapabilityRegistry",
    "Confirmation",
    "DefinitionError",
    "DuplicateCapabilityError",
    "FrozenCapabilityRegistry",
    "Idempotency",
    "InvocationError",
    "JsonSchema",

    "Policy",
    "PolicyFailure",
    "PolicyResult",
    "PolicySuccess",


    "Principal",
    "RegistryError",
    "RegistryFrozenError",
    "Risk",
    "SchemaAdapter",
    "SchemaError",
    "StandardEffect",
    "StandardSchemaAdapter",
    "TypeSchema",
    "UnknownCapabilityError",
    "ValidationError",
    "__version__",
]

