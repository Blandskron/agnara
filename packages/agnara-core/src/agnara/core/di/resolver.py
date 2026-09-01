import asyncio
import contextlib
from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from typing import Any

from .compiler import _get_dependencies
from .provider import ProviderType, Scope
from .registry import DIRegistry


class DIContainer:
    """
    A global DI container that holds the registry and singleton caches.
    """

    def __init__(self, registry: DIRegistry) -> None:
        self.registry = registry
        self.singleton_cache: dict[type, Any] = {}
        # Global exit stack for singleton cleanup
        self.exit_stack = contextlib.AsyncExitStack()
        self._lock = asyncio.Lock()

    async def aclose(self) -> None:
        """Close the container and cleanup singletons."""
        await self.exit_stack.aclose()
        self.singleton_cache.clear()

    @contextlib.asynccontextmanager
    async def resolve_dependencies(
        self,
        target_func: Callable[..., Any],
        target_deps: Mapping[Callable[..., Any], Sequence[type]],
    ) -> AsyncGenerator[dict[str, Any]]:
        """
        Resolve dependencies for a target function.

        Uses a local AsyncExitStack to ensure generator providers are safely torn down
        after the target function executes.
        Caches INVOCATION scoped providers locally.

        Yields a dictionary of kwargs to pass to the target function.
        """
        invocation_cache: dict[type, Any] = {}

        deps_required = target_deps.get(target_func, [])
        if not deps_required:
            yield {}
            return

        async with contextlib.AsyncExitStack() as invocation_stack:
            resolved_kwargs: dict[str, Any] = {}

            async def resolve_type(typ: type) -> Any:
                provider = self.registry.get_provider(typ)
                if not provider:
                    # Should be caught by DAG compiler
                    raise RuntimeError(f"Provider not found for {typ}")

                # Check caches
                if provider.scope == Scope.SINGLETON:
                    async with self._lock:
                        if typ in self.singleton_cache:
                            return self.singleton_cache[typ]
                elif provider.scope == Scope.INVOCATION and typ in invocation_cache:
                    return invocation_cache[typ]

                # Resolve sub-dependencies outside the lock
                sub_deps = _get_dependencies(provider.func)
                sub_kwargs = {}
                for name, sub_typ in sub_deps.items():
                    if self.registry.is_bound(sub_typ):
                        sub_kwargs[name] = await resolve_type(sub_typ)

                # Instantiate provider
                async def instantiate() -> Any:
                    if provider.provider_type == ProviderType.SYNC_FUNCTION:
                        return provider.func(**sub_kwargs)
                    elif provider.provider_type == ProviderType.ASYNC_FUNCTION:
                        return await provider.func(**sub_kwargs)
                    elif provider.provider_type == ProviderType.SYNC_GENERATOR:
                        if provider.scope == Scope.SINGLETON:
                            return self.exit_stack.enter_context(
                                contextlib.contextmanager(provider.func)(**sub_kwargs)
                            )
                        else:
                            return invocation_stack.enter_context(
                                contextlib.contextmanager(provider.func)(**sub_kwargs)
                            )
                    elif provider.provider_type == ProviderType.ASYNC_GENERATOR:
                        if provider.scope == Scope.SINGLETON:
                            return await self.exit_stack.enter_async_context(
                                contextlib.asynccontextmanager(provider.func)(**sub_kwargs)
                            )
                        else:
                            return await invocation_stack.enter_async_context(
                                contextlib.asynccontextmanager(provider.func)(**sub_kwargs)
                            )
                    else:
                        raise RuntimeError(f"Unknown provider type {provider.provider_type}")

                if provider.scope == Scope.SINGLETON:
                    async with self._lock:
                        # Double-check inside lock
                        if typ in self.singleton_cache:
                            return self.singleton_cache[typ]

                        instance = await instantiate()
                        self.singleton_cache[typ] = instance
                        return instance
                else:
                    instance = await instantiate()
                    invocation_cache[typ] = instance
                    return instance

            # Resolve direct dependencies
            target_hints = _get_dependencies(target_func)
            for name, typ in target_hints.items():
                if typ in deps_required:
                    resolved_kwargs[name] = await resolve_type(typ)

            yield resolved_kwargs
