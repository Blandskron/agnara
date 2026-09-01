"""The Agnara application: the composition root and authoring surface.

``Agnara`` is where a developer declares capabilities. It owns a
`CapabilityRegistry` and nothing else — no transport, no server, no
execution. `ARCHITECTURE.md` section 5 warns that the application object
must not become a god object, so this one deliberately does very little.

The decorator records a declaration. It does **not** wrap, replace or alter
the function's call behaviour: the function it returns is the function it
received. That keeps capabilities ordinary Python callables that a test can
call directly, and leaves execution entirely to EPIC 4.

    app = Agnara("payments")

    @app.capability
    def refund(payment_id: str) -> str:
        return "refunded"

    @app.capability(effects={"destructive"}, risk="high", confirmation="required")
    async def delete_account(user_id: str) -> None: ...
"""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable
from typing import Any, overload

from agnara.capability.definition import CapabilityDefinition, Handler
from agnara.capability.identity import CapabilityId
from agnara.capability.metadata import Confirmation, Idempotency, Risk
from agnara.capability.registry import CapabilityRegistry, FrozenCapabilityRegistry
from agnara.errors import DefinitionError

__all__ = ["Agnara"]


def _describe(handler: Handler) -> str | None:
    """Use the handler's docstring summary when no description is given.

    Agent consumers need a description to decide whether a capability is the
    one they want (PRINCIPLES.md P10). Requiring every declaration to repeat
    the docstring would guarantee the two drift apart, so the docstring is
    the default and an explicit ``description`` always wins.

    Only the first paragraph is taken; the rest is implementation detail for
    a human reading the source.
    """
    doc = inspect.getdoc(handler)
    if not doc:
        return None
    summary = doc.split("\n\n", 1)[0].strip()
    return summary or None


def _idempotency_from(idempotent: bool | None) -> Idempotency:
    """Map the authoring surface's boolean onto the honest tri-state.

    ``docs/API_DESIGN.md`` section 11 writes ``idempotent=False``, which is
    the natural way to say it. The model keeps three states because RFC 0001
    requires that silence mean ``UNKNOWN`` rather than a false claim, so
    omitting the argument is not the same as passing ``False``.
    """
    if idempotent is None:
        return Idempotency.UNKNOWN
    return Idempotency.YES if idempotent else Idempotency.NO


class Agnara:
    """An Agnara application: a namespace, a registry, and a decorator.

    The application name becomes the namespace of every capability declared
    on it, so ``Agnara("payments")`` produces ids like ``payments.refund``.
    """

    __slots__ = ("_name", "_registry")

    def __init__(self, name: str) -> None:
        if not isinstance(name, str):
            raise DefinitionError(f"application name must be a string, got {type(name).__name__}")
        if not name:
            raise DefinitionError("application name must not be empty")
        # Validate through CapabilityId so there is one rule for what a
        # namespace may look like, rather than two that can drift apart.
        # The probe name never escapes; only the namespace verdict matters.
        try:
            CapabilityId(namespace=name, name="probe")
        except DefinitionError as exc:
            raise DefinitionError(
                f"invalid application name {name!r}: it becomes the namespace of "
                "every capability declared on it, so it must be a single Python identifier"
            ) from exc
        self._name = name
        self._registry = CapabilityRegistry()

    @property
    def name(self) -> str:
        """The application name, which is the namespace of its capabilities."""
        return self._name

    @property
    def capabilities(self) -> CapabilityRegistry:
        """The registry of declared capabilities.

        Read-only in practice during authoring; call :meth:`compile` to get
        the immutable view that is safe to share after startup.
        """
        return self._registry

    @property
    def is_compiled(self) -> bool:
        """Whether :meth:`compile` has closed registration."""
        return self._registry.is_frozen

    @overload
    def capability[F: Handler](self, handler: F, /) -> F: ...

    @overload
    def capability[F: Handler](
        self,
        /,
        *,
        name: str | None = None,
        description: str | None = None,
        scopes: Iterable[str] = (),
        effects: Iterable[str] = (),
        risk: Risk | str = Risk.LOW,
        confirmation: Confirmation | str = Confirmation.NEVER,
        idempotent: bool | None = None,
    ) -> Callable[[F], F]: ...

    def capability(
        self,
        handler: Any = None,
        /,
        *,
        name: str | None = None,
        description: str | None = None,
        scopes: Iterable[str] = (),
        effects: Iterable[str] = (),
        risk: Risk | str = Risk.LOW,
        confirmation: Confirmation | str = Confirmation.NEVER,
        idempotent: bool | None = None,
    ) -> Any:
        """Declare a capability, bare or with metadata.

        Both forms work::

            @app.capability
            def refund(...): ...

            @app.capability(risk="high")
            def delete_account(...): ...

        The function is returned unchanged, so it remains directly callable
        and directly testable. Registration is a side effect on the
        application, not a transformation of the function.

        The capability id defaults to ``<app name>.<function name>``. Pass
        ``name`` to override it, which RFC 0001 requires so that renaming a
        Python function does not silently change an id that policies, audit
        records and agent manifests refer to.
        """

        def declare[F: Handler](func: F) -> F:
            if not callable(func):
                raise DefinitionError(
                    f"@{self._name}.capability expects a callable, got {type(func).__name__}"
                )
            self._registry.register(
                CapabilityDefinition.declare(
                    id=CapabilityId(
                        namespace=self._name,
                        name=name if name is not None else getattr(func, "__name__", ""),
                    ),
                    handler=func,
                    description=description if description is not None else _describe(func),
                    scopes=scopes,
                    effects=effects,
                    risk=risk,
                    confirmation=confirmation,
                    idempotency=_idempotency_from(idempotent),
                )
            )
            return func

        # Bare `@app.capability` passes the function positionally; the called
        # form passes nothing and must return the decorator itself.
        if handler is None:
            return declare
        return declare(handler)

    def compile(self) -> FrozenCapabilityRegistry:
        """Close registration and return the immutable capability view.

        This is the freeze step ADR 0005 places at the end of startup
        compilation. Later phases — schemas, dependencies, policies,
        exposures — will hang off this method as they are implemented.
        """
        return self._registry.freeze()

    def __repr__(self) -> str:
        state = "compiled" if self.is_compiled else "open"
        return f"Agnara({self._name!r}, {len(self._registry)} capabilities, {state})"
