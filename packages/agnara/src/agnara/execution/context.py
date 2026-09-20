import asyncio
from typing import Any

from agnara.core.di.resolver import DIContainer
from agnara.errors import DefinitionError
from agnara.execution._execution_identity import ExecutionId
from agnara.execution.idempotency import IdempotencyInvocation
from agnara.execution.invocation import Invocation
from agnara.policy.confirmation import ConfirmationEvidence
from agnara.policy.principal import AnonymousPrincipal, Principal

__all__: list[str] = []


# This matches the reviewed MCP request-correlation ceiling.  Nested
# composition does not need a second caller-controlled cardinality channel.
_MAX_COMPOSITION_TRACKING_ID = 128


class ExecutionContext:
    """The active runtime environment for a single capability execution.

    Holds the transport-neutral context required to evaluate policies, resolve
    dependencies, and execute a compiled plan.
    """

    def __init__(
        self,
        invocation: Invocation,
        di_container: DIContainer,
        tracking_id: str | None = None,
        principal: Principal | None = None,
        confirmation_evidence: ConfirmationEvidence | None = None,
        idempotency: IdempotencyInvocation | None = None,
    ) -> None:
        self.invocation = invocation
        self.di_container = di_container
        if "execution_id" in invocation.metadata:
            raise DefinitionError(
                "execution_id is runtime-owned and must not be supplied through invocation metadata"
            )
        self._execution_id = ExecutionId.generate()
        self.tracking_id = tracking_id
        self.principal = principal or AnonymousPrincipal()
        if confirmation_evidence is not None and not isinstance(
            confirmation_evidence, ConfirmationEvidence
        ):
            raise TypeError("confirmation_evidence must be ConfirmationEvidence or None")
        self.confirmation_evidence = confirmation_evidence
        if idempotency is not None and not isinstance(idempotency, IdempotencyInvocation):
            raise TypeError("idempotency must be IdempotencyInvocation or None")
        self.idempotency = idempotency
        # Runtime-owned nested-composition values. A handler must not be able
        # to manufacture ancestry, a causal link, or an aliased child scope.
        self._composition_ancestry: tuple[object, ...] = ()
        self._parent_execution_id: str | None = None
        # State that policies or interceptors might attach during this execution.
        # This is strictly bound to a single capability execution.
        self.state: dict[str, Any] = {}

    @property
    def execution_id(self) -> str:
        """The opaque logical identity for this execution.

        It is distinct from optional caller correlation (``tracking_id``) and
        the telemetry-only ``invocation_id``.  Reusing this context deliberately
        retains the same execution identity while each runtime invocation gets
        its own telemetry attempt identity (ADR 0087).
        """
        return str(self._execution_id)

    @property
    def deadline(self) -> float | None:
        """The invocation's absolute monotonic deadline, when one exists."""
        return self.invocation.deadline

    def remaining_time(self, now: float | None = None) -> float | None:
        """Seconds remaining, clamped to zero, or ``None`` without a deadline."""
        if self.deadline is None:
            return None
        current = asyncio.get_running_loop().time() if now is None else now
        return max(0.0, self.deadline - current)

    def _adopt_idempotency_execution_id(self, execution_id: str) -> None:
        """Replace the provisional context identity with the claimed logical ID.

        Only the runtime calls this after an atomic claim or completed lookup;
        it is deliberately not an application or transport input channel.
        """
        self._execution_id = ExecutionId(execution_id)

    @classmethod
    def _child(cls, parent: ExecutionContext, invocation: Invocation) -> ExecutionContext:
        """Derive one isolated direct-actor child for nested composition.

        RFC 0005 delegation is not implemented.  The child therefore receives
        a detached copy of the authenticated actor, not a subject, delegation
        chain, raw evidence, confirmation or an ambient authority object.
        Target policies evaluate the child's direct actor independently.
        """
        principal = _copy_direct_actor(parent.principal)
        child = cls(
            invocation,
            parent.di_container,
            tracking_id=_child_tracking_id(parent.tracking_id),
            principal=principal,
        )
        child._composition_ancestry = (
            *parent._composition_ancestry,
            parent.invocation.capability_id,
        )
        child._parent_execution_id = parent.execution_id
        return child


def _copy_direct_actor(principal: Principal) -> Principal:
    """Detach the direct actor input without introducing delegation semantics."""
    return Principal(
        principal.identity,
        metadata=principal.metadata,
        scopes=principal.scopes,
    )


def _child_tracking_id(value: object) -> str | None:
    """Retain only a bounded correlation label for a nested lifecycle."""
    if isinstance(value, str) and len(value) <= _MAX_COMPOSITION_TRACKING_ID:
        return value
    return None
