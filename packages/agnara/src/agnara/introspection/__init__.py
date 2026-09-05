"""Protocol-neutral introspection: one snapshot every surface can read.

`ARCHITECTURE.md` section 10 and RFC 0003 give the CLI, an authorized
discovery endpoint and Agnara Explorer the same source of truth, so none of
them derives its answers from OpenAPI or from another surface's projection.

This package defines the snapshot and builds it from a compiled application.
It does not decide what a viewer may see: visibility, redaction and
authorization filter this model before serialization (E8.2).
"""

from .builder import describe_app, snapshot
from .descriptors import (
    INTROSPECTION_FORMAT,
    INTROSPECTION_VERSION,
    AppDescriptor,
    CapabilityDescriptor,
    DependencyDescriptor,
    ExposureDescriptor,
    InputDescriptor,
    IntrospectionError,
    IntrospectionSnapshot,
    PolicyDescriptor,
    ProviderDescriptor,
    TypeReference,
)

__all__ = [
    "INTROSPECTION_FORMAT",
    "INTROSPECTION_VERSION",
    "AppDescriptor",
    "CapabilityDescriptor",
    "DependencyDescriptor",
    "ExposureDescriptor",
    "InputDescriptor",
    "IntrospectionError",
    "IntrospectionSnapshot",
    "PolicyDescriptor",
    "ProviderDescriptor",
    "TypeReference",
    "describe_app",
    "snapshot",
]
