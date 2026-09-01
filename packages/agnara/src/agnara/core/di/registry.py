from collections.abc import Callable
from typing import Any

from .provider import ProviderDefinition


class DIRegistry:
    """A registry for dependency providers."""

    def __init__(self) -> None:
        self._providers: dict[type, ProviderDefinition] = {}

    def bind(self, provides: type, provider: ProviderDefinition | Callable[..., Any]) -> None:
        """Bind a type to a provider."""
        if not isinstance(provider, ProviderDefinition):
            # Try to infer it's a provider without explicit decorator if possible?
            # For now, require ProviderDefinition.
            raise TypeError("provider must be a ProviderDefinition created via @provider")

        self._providers[provides] = provider

    def get_provider(self, provides: type) -> ProviderDefinition | None:
        """Get the provider for a type."""
        return self._providers.get(provides)

    def is_bound(self, provides: type) -> bool:
        """Check if a type is bound to a provider."""
        return provides in self._providers

    def all_bindings(self) -> dict[type, ProviderDefinition]:
        return self._providers.copy()
