from collections.abc import Iterable, Mapping
from dataclasses import field
from typing import Any

from agnara._frozen import frozen_slots_dataclass
from agnara.policy.scopes import _normalize_scopes

__all__ = ["AnonymousPrincipal", "Principal"]


@frozen_slots_dataclass
class Principal:
    """Represents an authenticated entity invoking a capability.

    The identity string is a stable, unique identifier for the principal.
    Metadata can contain arbitrary safe key-value pairs required by policies.
    Scopes are explicit permission labels granted by the authentication boundary.
    """

    identity: str
    metadata: dict[str, Any] = field(default_factory=dict)
    scopes: frozenset[str] = field(default_factory=frozenset)

    def __init__(
        self,
        identity: str,
        metadata: Mapping[str, Any] | None = None,
        scopes: Iterable[str] = (),
    ) -> None:
        object.__setattr__(self, "identity", identity)
        object.__setattr__(self, "metadata", dict(metadata or {}))
        object.__setattr__(self, "scopes", _normalize_scopes(scopes, "principal scopes"))


@frozen_slots_dataclass
class AnonymousPrincipal(Principal):
    """Represents an unauthenticated invocation with no granted scopes."""

    identity: str = "anonymous"

    def __init__(
        self,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        Principal.__init__(self, "anonymous", metadata, ())
