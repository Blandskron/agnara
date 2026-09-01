"""Stable, transport-neutral capability identity.

A capability's identity must survive refactors, must not depend on how the
capability happens to be exposed, and must be stable enough to appear in
policy rules, audit logs and agent-facing manifests. RFC 0001 defines the
default shape as::

    <application-namespace>.<python-qualified-name>

so an id is a namespace plus a name, joined by a dot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from agnara.errors import DefinitionError

__all__ = ["CapabilityId"]

SEPARATOR: Final = "."


def _validate_segment(segment: str, *, part: str, whole: str) -> None:
    if not segment:
        raise DefinitionError(
            f"invalid capability {part} in {whole!r}: "
            f"segments must not be empty, so {whole!r} cannot contain "
            f"a leading, trailing or doubled {SEPARATOR!r}"
        )
    if not segment.isidentifier():
        raise DefinitionError(
            f"invalid capability {part} in {whole!r}: "
            f"{segment!r} is not a valid Python identifier"
        )


@dataclass(frozen=True, slots=True)
class CapabilityId:
    """The stable logical name of one capability.

    ``namespace`` is a single identifier naming the owning app or
    application namespace, such as ``payments``. ``name`` identifies the
    capability within it and may be dotted, because a Python qualified name
    can be, as in ``Refunds.create``.

    Instances are frozen, hashable and safe to share across threads.
    """

    namespace: str
    name: str

    def __post_init__(self) -> None:
        whole = str(self)
        # Check for a dotted namespace before the generic segment check, so
        # that `commerce.payments` reports the actual mistake rather than
        # the less useful "not a valid Python identifier".
        if SEPARATOR in self.namespace:
            raise DefinitionError(
                f"invalid capability namespace in {whole!r}: "
                f"{self.namespace!r} must be a single segment, because the "
                f"first {SEPARATOR!r} separates the namespace from the name"
            )
        _validate_segment(self.namespace, part="namespace", whole=whole)
        if not self.name:
            raise DefinitionError(
                f"invalid capability name in {whole!r}: the name must not be empty"
            )
        for segment in self.name.split(SEPARATOR):
            _validate_segment(segment, part="name", whole=whole)

    @classmethod
    def parse(cls, text: str) -> CapabilityId:
        """Build an id from its dotted string form.

        The **first** separator splits namespace from name, so
        ``"payments.Refunds.create"`` is the ``Refunds.create`` capability
        of the ``payments`` namespace. Splitting on the last separator
        instead would make a dotted qualified name ambiguous.
        """
        if SEPARATOR not in text:
            expected = f"<namespace>{SEPARATOR}<name>"
            raise DefinitionError(
                f"invalid capability id {text!r}: expected {expected}, "
                f"but found no {SEPARATOR!r}"
            )
        namespace, _, name = text.partition(SEPARATOR)
        return cls(namespace=namespace, name=name)

    def __str__(self) -> str:
        return f"{self.namespace}{SEPARATOR}{self.name}"
