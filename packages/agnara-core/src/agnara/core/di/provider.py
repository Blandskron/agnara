import enum
import inspect
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any, get_args, get_origin

from agnara._frozen import frozen_slots_dataclass


class Scope(enum.Enum):
    """Execution scope for a dependency provider."""

    SINGLETON = "singleton"
    INVOCATION = "invocation"


class ProviderType(enum.Enum):
    """The type of the provider callable."""

    SYNC_FUNCTION = "sync_function"
    ASYNC_FUNCTION = "async_function"
    SYNC_GENERATOR = "sync_generator"
    ASYNC_GENERATOR = "async_generator"


@frozen_slots_dataclass
class ProviderDefinition:
    """Immutable definition of a provider and its scope."""

    func: Callable[..., Any]
    scope: Scope
    provider_type: ProviderType
    return_type: type

    @classmethod
    def from_callable(cls, func: Callable[..., Any], scope: Scope) -> ProviderDefinition:
        if inspect.isasyncgenfunction(func):
            provider_type = ProviderType.ASYNC_GENERATOR
        elif inspect.isgeneratorfunction(func):
            provider_type = ProviderType.SYNC_GENERATOR
        elif inspect.iscoroutinefunction(func):
            provider_type = ProviderType.ASYNC_FUNCTION
        else:
            provider_type = ProviderType.SYNC_FUNCTION

        sig = inspect.signature(func)
        func_name = getattr(func, "__name__", repr(func))
        if sig.return_annotation is inspect.Signature.empty:
            raise TypeError(f"Provider {func_name} must declare a return type hint.")

        return_type = sig.return_annotation
        # If it's a generator, the injected type is the yielded type
        # (first arg of Iterator/AsyncIterator)
        origin = get_origin(return_type)
        if origin in (Iterator, AsyncIterator):
            args = get_args(return_type)
            if not args:
                raise TypeError(
                    f"Provider {func_name} Iterator/AsyncIterator must be parameterized."
                )
            return_type = args[0]
        # Same for Generator/AsyncGenerator (typing.Generator / typing.AsyncGenerator)
        # Note: In Python 3.14, typing.Generator is deprecated in favor of collections.abc.Generator
        elif origin is not None and getattr(origin, "__name__", "") in (
            "Generator",
            "AsyncGenerator",
        ):
            args = get_args(return_type)
            if not args:
                raise TypeError(
                    f"Provider {func_name} Generator/AsyncGenerator must be parameterized."
                )
            return_type = args[0]

        return cls(
            func=func,
            scope=scope,
            provider_type=provider_type,
            return_type=return_type,
        )


def provider(
    *, scope: Scope = Scope.INVOCATION
) -> Callable[[Callable[..., Any]], ProviderDefinition]:
    """
    Decorator to mark a function or generator as a dependency provider.

    Returns a ProviderDefinition which is statically compiled into the DI graph.
    """

    def decorator(func: Callable[..., Any]) -> ProviderDefinition:
        return ProviderDefinition.from_callable(func, scope)

    return decorator
