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

from collections.abc import Callable, Iterable
from typing import Any, overload

from agnara._declaration import declare_into, validated_namespace
from agnara.app import App
from agnara.capability.definition import Handler
from agnara.capability.metadata import Confirmation, Risk
from agnara.capability.registry import CapabilityRegistry, FrozenCapabilityRegistry
from agnara.errors import DefinitionError

__all__ = ["Agnara"]


class Agnara:
    """An Agnara application: a namespace, a registry, and a decorator.

    The application name becomes the namespace of every capability declared
    on it, so ``Agnara("payments")`` produces ids like ``payments.refund``.
    """

    __slots__ = ("_name", "_registry")

    def __init__(self, name: str) -> None:
        self._name = validated_namespace(name, subject="application")
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
            declare_into(
                self._registry,
                namespace=self._name,
                owner=self._name,
                func=func,
                name=name,
                description=description,
                scopes=scopes,
                effects=effects,
                risk=risk,
                confirmation=confirmation,
                idempotent=idempotent,
            )
            return func

        # Bare `@app.capability` passes the function positionally; the called
        # form passes nothing and must return the decorator itself.
        if handler is None:
            return declare
        return declare(handler)

    def include(self, app: App) -> App:
        """Mount an app's capabilities on this application.

        The app keeps its own namespace, so a capability declared on
        ``App("payments")`` is ``payments.get_record`` however many projects
        mount it. That is what lets two apps from the same scaffold coexist:
        they declare the same names in different bounded contexts.

        Args:
            app: the declared app to mount.

        Returns:
            `app`, so a composition root can mount and keep a reference in
            one statement.

        Raises:
            DefinitionError: `app` is not an `App`.
            RegistryFrozenError: this application has already compiled.
            DuplicateCapabilityError: two mounted apps claim the same
                capability id, which can only happen if they share a name.
        """
        if not isinstance(app, App):
            raise DefinitionError(f"{self._name}.include expects an App, got {type(app).__name__}")
        declarations = app.capabilities
        for capability_id in declarations:
            self._registry.register(declarations[capability_id])
        return app

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
