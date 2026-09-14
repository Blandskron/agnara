"""An app: one bounded context, and the capabilities it owns.

ADR 0011 decides that an Agnara app is a bounded context such as `payments`
or `catalog`, never a protocol type. `ARCHITECTURE.md` section 13 places it
between the project and its capabilities. This module is the runtime for that
decision, and it answers the first open question in RFC 0002, "exact app
descriptor API".

An app declares; a project mounts::

    # src/shop/apps/payments/module.py
    payments = App("payments")


    @payments.capability(description="Read one record.", idempotent=True)
    def get_record(reference: str) -> dict[str, str]: ...


    def register(app: Agnara, dependencies: DIRegistry) -> None:
        app.include(payments)

The app name becomes the capability namespace, so the id is
``payments.get_record``. The **project** name does not appear in it:
`CapabilityId` is a namespace and a name, and its namespace is documented as
the owning app. That is what lets two apps from the same scaffold coexist,
and it means renaming a project cannot change ids that policies, audit records
and agent manifests refer to.

Declaration is separate from mounting on purpose. An app can be imported,
inspected and unit-tested without a project, and a project decides what it
contains in one place.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any, overload

from agnara._declaration import declare_into, validated_namespace
from agnara._frozen import frozen_slots_dataclass
from agnara.capability.definition import Handler
from agnara.capability.metadata import Confirmation, Risk
from agnara.capability.registry import CapabilityRegistry
from agnara.errors import DefinitionError

__all__ = ["App", "AppDescriptor"]


def _validated_module(module: str | None) -> str | None:
    """Check an optional dotted import path.

    Not required: an app is identified by its name. When given it says where
    the app lives, which `agnara.toml` also records and which introspection
    will want in order to point a reader at the source.
    """
    if module is None:
        return None
    if not isinstance(module, str):
        raise DefinitionError(f"app module must be a string, got {type(module).__name__}")
    if not module:
        raise DefinitionError("app module must not be empty when given")
    for segment in module.split("."):
        if not segment.isidentifier():
            raise DefinitionError(
                f"invalid app module {module!r}: {segment!r} is not a valid Python identifier"
            )
    return module


@frozen_slots_dataclass
class AppDescriptor:
    """The identity of one app, independent of what it contains.

    Frozen and hashable, so it is safe to share and safe to use as a key when
    a project needs to talk about its apps rather than their capabilities.

    Attributes:
        name: the bounded context, a single Python identifier. It becomes the
            namespace of every capability the app declares.
        description: what the context is for, for a human or an agent reading
            an introspection snapshot.
        module: the dotted import path the app lives at, when known.
    """

    name: str
    description: str | None = None
    module: str | None = None

    def __post_init__(self) -> None:
        validated_namespace(self.name, subject="app")
        if self.description is not None and not isinstance(self.description, str):
            raise DefinitionError(
                f"app description must be a string or None, got {type(self.description).__name__}"
            )
        _validated_module(self.module)

    def __str__(self) -> str:
        return self.name


class App:
    """One bounded context: a descriptor, a registry, and a decorator.

    The declaration surface. It holds what the app owns and knows nothing
    about the project that will mount it, which is what keeps an app testable
    on its own.

    Registration stays open until a project compiles. An `App` has no
    ``compile`` of its own: freezing is a project-wide decision that ADR 0005
    places at the end of startup, and an app that could freeze itself would
    let one module close a registry another module was still writing to.
    """

    __slots__ = ("_descriptor", "_registry")

    def __init__(
        self,
        name: str,
        *,
        description: str | None = None,
        module: str | None = None,
    ) -> None:
        self._descriptor = AppDescriptor(name=name, description=description, module=module)
        self._registry = CapabilityRegistry()

    @property
    def descriptor(self) -> AppDescriptor:
        """This app's identity."""
        return self._descriptor

    @property
    def name(self) -> str:
        """The app name, which is the namespace of its capabilities."""
        return self._descriptor.name

    @property
    def capabilities(self) -> CapabilityRegistry:
        """The capabilities declared on this app, before any project mounts it."""
        return self._registry

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
        streaming: bool = False,
        output: object = Any,
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
        streaming: bool = False,
        output: object = Any,
    ) -> Any:
        """Declare a capability owned by this app.

        Identical to ``Agnara.capability`` in every respect but the namespace,
        which is this app's name. The function is returned unchanged, so it
        stays directly callable and directly testable.
        """

        def declare[F: Handler](func: F) -> F:
            declare_into(
                self._registry,
                namespace=self._descriptor.name,
                owner=self._descriptor.name,
                func=func,
                name=name,
                description=description,
                scopes=scopes,
                effects=effects,
                risk=risk,
                confirmation=confirmation,
                idempotent=idempotent,
                streaming=streaming,
                output=output,
            )
            return func

        if handler is None:
            return declare
        return declare(handler)

    def __repr__(self) -> str:
        return f"App({self._descriptor.name!r}, {len(self._registry)} capabilities)"
