"""Protocol-neutral introspection: one snapshot every surface can read.

`ARCHITECTURE.md` section 10 and RFC 0003 give the CLI, an authorized
discovery endpoint and Agnara Explorer the same source of truth, so none of
them derives its answers from OpenAPI or from another surface's projection.

This package defines the snapshot and builds it from a compiled application.
It also decides what one viewer may see: ``filter_snapshot`` applies a
``DiscoveryVisibility`` before anything is serialized, because filtering a
serialized document leaks through references and derived values.
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
from .visibility import (
    AllCapabilitiesVisible,
    DiscoveryField,
    DiscoveryVisibility,
    Hiding,
    NoCapabilityVisible,
    ScopeVisible,
    VisibilityRule,
    filter_snapshot,
)

__all__ = [
    "INTROSPECTION_FORMAT",
    "INTROSPECTION_VERSION",
    "AllCapabilitiesVisible",
    "AppDescriptor",
    "CapabilityDescriptor",
    "DependencyDescriptor",
    "DiscoveryField",
    "DiscoveryVisibility",
    "ExposureDescriptor",
    "Hiding",
    "InputDescriptor",
    "IntrospectionError",
    "IntrospectionSnapshot",
    "NoCapabilityVisible",
    "PolicyDescriptor",
    "ProviderDescriptor",
    "ScopeVisible",
    "TypeReference",
    "VisibilityRule",
    "describe_app",
    "filter_snapshot",
    "snapshot",
]
