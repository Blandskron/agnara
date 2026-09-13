"""How a capability declaration is built, shared by every authoring surface.

``Agnara`` and ``App`` both offer a ``capability`` decorator with identical
semantics and a different namespace. The typed signature has to be repeated on
each -- overloads cannot be inherited usefully -- but the behaviour must not
be, or the two surfaces would drift and a capability would mean something
slightly different depending on where it was declared.

Nothing here is public. See ``agnara.application`` and ``agnara.app``.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterable

from agnara.capability.definition import CapabilityDefinition, Handler
from agnara.capability.identity import CapabilityId
from agnara.capability.metadata import Confirmation, Idempotency, Risk
from agnara.capability.registry import CapabilityRegistry
from agnara.errors import DefinitionError

__all__ = ["declare_into", "describe", "idempotency_from", "validated_namespace"]


def describe(handler: Handler) -> str | None:
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


def idempotency_from(idempotent: bool | None) -> Idempotency:
    """Map the authoring surface's boolean onto the honest tri-state.

    ``docs/API_DESIGN.md`` section 11 writes ``idempotent=False``, which is
    the natural way to say it. The model keeps three states because RFC 0001
    requires that silence mean ``UNKNOWN`` rather than a false claim, so
    omitting the argument is not the same as passing ``False``.
    """
    if idempotent is None:
        return Idempotency.UNKNOWN
    return Idempotency.YES if idempotent else Idempotency.NO


def validated_namespace(name: str, *, subject: str) -> str:
    """Check a name that will become a capability namespace.

    Validated through `CapabilityId` so there is one rule for what a
    namespace may look like, rather than two that can drift apart. The probe
    name never escapes; only the namespace verdict matters.

    Args:
        name: the candidate namespace.
        subject: what to call it in a diagnostic, such as ``"application"``.

    Returns:
        `name`, unchanged.

    Raises:
        DefinitionError: `name` is not a string, is empty, or is not a single
            Python identifier.
    """
    if not isinstance(name, str):
        raise DefinitionError(f"{subject} name must be a string, got {type(name).__name__}")
    if not name:
        raise DefinitionError(f"{subject} name must not be empty")
    try:
        CapabilityId(namespace=name, name="probe")
    except DefinitionError as error:
        raise DefinitionError(
            f"invalid {subject} name {name!r}: it becomes the namespace of "
            "every capability declared on it, so it must be a single Python identifier"
        ) from error
    return name


def declare_into(
    registry: CapabilityRegistry,
    *,
    namespace: str,
    owner: str,
    func: object,
    name: str | None,
    description: str | None,
    scopes: Iterable[str],
    effects: Iterable[str],
    risk: Risk | str,
    confirmation: Confirmation | str,
    idempotent: bool | None,
    streaming: bool,
    output: object,
) -> None:
    """Register one declaration, or say which surface refused it.

    `owner` appears in the diagnostic so a reader is pointed at the decorator
    they actually wrote, rather than at this shared helper.

    Raises:
        DefinitionError: `func` is not callable.
    """
    if not callable(func):
        raise DefinitionError(f"@{owner}.capability expects a callable, got {type(func).__name__}")
    registry.register(
        CapabilityDefinition.declare(
            id=CapabilityId(
                namespace=namespace,
                name=name if name is not None else getattr(func, "__name__", ""),
            ),
            handler=func,
            description=description if description is not None else describe(func),
            scopes=scopes,
            effects=effects,
            risk=risk,
            confirmation=confirmation,
            idempotency=idempotency_from(idempotent),
            streaming=streaming,
            output=output,
        )
    )
