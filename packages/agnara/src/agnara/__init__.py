"""Agnara — a capability-first, transport-neutral execution kernel.

``agnara-core`` owns the semantics shared by every transport: the capability
model, the registry, execution context, the dependency graph, policies,
execution planning and canonical errors.

It must never import a protocol implementation, a server, a schema library
or an LLM SDK. See ``ARCHITECTURE.md`` section 3 and ``PRINCIPLES.md`` P2.

Currently implemented: capability declaration and registration, schema ports,
dependency compilation/resolution, execution plans, direct invocation, and
pre-handler policy orchestration. Transport adapters remain ahead in
``BACKLOG.md``.
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
    InteractionRequiredError,
    InvocationError,
    PolicyDeniedError,
    RegistryError,
    RegistryFrozenError,
    SchemaError,
    UnknownCapabilityError,
    ValidationError,
)
from agnara.policy import (
    AnonymousPrincipal,
    ConfirmationEvidence,
    ConfirmationVerdict,
    ConfirmationVerifier,
    InteractionKind,
    InteractionRequest,
    Policy,
    PolicyFailure,
    PolicyInteractionRequired,
    PolicyResult,
    PolicySuccess,
    Principal,
    ScopePolicy,
)
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
    "ConfirmationEvidence",
    "ConfirmationVerdict",
    "ConfirmationVerifier",
    "DefinitionError",
    "DuplicateCapabilityError",
    "FrozenCapabilityRegistry",
    "Idempotency",
    "InteractionKind",
    "InteractionRequest",
    "InteractionRequiredError",
    "InvocationError",
    "JsonSchema",
    "Policy",
    "PolicyDeniedError",
    "PolicyFailure",
    "PolicyInteractionRequired",
    "PolicyResult",
    "PolicySuccess",
    "Principal",
    "RegistryError",
    "RegistryFrozenError",
    "Risk",
    "SchemaAdapter",
    "SchemaError",
    "ScopePolicy",
    "StandardEffect",
    "StandardSchemaAdapter",
    "TypeSchema",
    "UnknownCapabilityError",
    "ValidationError",
    "__version__",
]
