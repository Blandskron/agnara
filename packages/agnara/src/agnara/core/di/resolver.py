import asyncio
import contextlib
from collections.abc import AsyncGenerator, Callable, Mapping, Sequence
from typing import Any

from .compiler import _get_dependencies
from .provider import ProviderDefinition, ProviderType, Scope
from .registry import DIRegistry

#: The bound parameters of one callable: ``(parameter name, dependency type)``
#: in signature order, keeping only parameters whose type the registry binds.
type _Bindings = tuple[tuple[str, type], ...]


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
        # Callable -> its bound parameters. Type hints are resolved through
        # ``typing.get_type_hints``, which evaluates annotations and costs a
        # few microseconds per callable; resolving them on every invocation
        # dominated dependency resolution. The answer for one callable never
        # changes while the registry it was computed against is in use, so a
        # racing writer under free-threaded CPython can only store the same
        # value twice.
        self._bindings: dict[Callable[..., Any], _Bindings] = {}

    async def aclose(self) -> None:
        """Close the container and cleanup singletons."""
        await self.exit_stack.aclose()
        self.singleton_cache.clear()

    def _bound_parameters(self, func: Callable[..., Any]) -> _Bindings:
        bindings = self._bindings.get(func)
        if bindings is None:
            bindings = tuple(
                (name, typ)
                for name, typ in _get_dependencies(func).items()
                if self.registry.is_bound(typ)
            )
            self._bindings[func] = bindings
        return bindings

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
        deps_required = target_deps.get(target_func, ())
        if not deps_required:
            yield {}
            return

        async with contextlib.AsyncExitStack() as invocation_stack:
            invocation_cache: dict[type, Any] = {}
            resolved_kwargs: dict[str, Any] = {}
            for name, typ in self._bound_parameters(target_func):
                if typ in deps_required:
                    resolved_kwargs[name] = await self._resolve(
                        typ, invocation_cache, invocation_stack
                    )
            yield resolved_kwargs

    async def _resolve(
        self,
        typ: type,
        invocation_cache: dict[type, Any],
        invocation_stack: contextlib.AsyncExitStack,
    ) -> Any:
        provider = self.registry.get_provider(typ)
        if provider is None:
            # Should be caught by DAG compiler
            raise RuntimeError(f"Provider not found for {typ}")

        singleton = provider.scope is Scope.SINGLETON
        if singleton:
            # Reading the cache needs no lock: a dictionary read is atomic and
            # a cached singleton is never replaced. The lock only serializes
            # instantiation, so concurrent first callers build one instance.
            cached = self.singleton_cache.get(typ, _MISSING)
            if cached is not _MISSING:
                return cached
        elif typ in invocation_cache:
            return invocation_cache[typ]

        # Resolve sub-dependencies outside the lock
        sub_kwargs: dict[str, Any] = {}
        for name, sub_typ in self._bound_parameters(provider.func):
            sub_kwargs[name] = await self._resolve(sub_typ, invocation_cache, invocation_stack)

        if singleton:
            async with self._lock:
                # Double-check inside lock
                cached = self.singleton_cache.get(typ, _MISSING)
                if cached is not _MISSING:
                    return cached
                instance = await self._instantiate(provider, sub_kwargs, self.exit_stack)
                self.singleton_cache[typ] = instance
                return instance

        instance = await self._instantiate(provider, sub_kwargs, invocation_stack)
        invocation_cache[typ] = instance
        return instance

    @staticmethod
    async def _instantiate(
        provider: ProviderDefinition,
        kwargs: dict[str, Any],
        stack: contextlib.AsyncExitStack,
    ) -> Any:
        provider_type = provider.provider_type
        if provider_type is ProviderType.SYNC_FUNCTION:
            return provider.func(**kwargs)
        if provider_type is ProviderType.ASYNC_FUNCTION:
            return await provider.func(**kwargs)
        if provider_type is ProviderType.SYNC_GENERATOR:
            return stack.enter_context(contextlib.contextmanager(provider.func)(**kwargs))
        if provider_type is ProviderType.ASYNC_GENERATOR:
            return await stack.enter_async_context(
                contextlib.asynccontextmanager(provider.func)(**kwargs)
            )
        raise RuntimeError(f"Unknown provider type {provider_type}")


_MISSING: Any = object()
