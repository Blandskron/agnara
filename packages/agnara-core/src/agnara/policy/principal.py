from dataclasses import field
from typing import Any

from agnara.core.dataclasses import frozen_slots_dataclass

__all__ = ["AnonymousPrincipal", "Principal"]


@frozen_slots_dataclass
class Principal:
    """Represents an authenticated entity invoking a capability.

    The identity string is a stable, unique identifier for the principal.
    Metadata can contain arbitrary safe key-value pairs required by policies.
    """

    identity: str
    metadata: dict[str, Any] = field(default_factory=dict)


@frozen_slots_dataclass
class AnonymousPrincipal(Principal):
    """Represents an unauthenticated or anonymous invocation."""

    identity: str = "anonymous"
