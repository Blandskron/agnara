"""Transport-neutral scope authorization policy."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from agnara._frozen import frozen_slots_dataclass
from agnara.errors import DefinitionError
from agnara.policy.base import PolicyFailure, PolicyResult, PolicySuccess

if TYPE_CHECKING:
    from agnara.execution.context import ExecutionContext

__all__ = ["ScopePolicy"]


def _normalize_scopes(values: Iterable[str], field_name: str) -> frozenset[str]:
    if isinstance(values, str):
        raise DefinitionError(f"{field_name} must be a collection of strings")
    try:
        scopes = frozenset(values)
    except TypeError as exc:
        raise DefinitionError(f"{field_name} must be an iterable of strings: {exc}") from exc
    for scope in scopes:
        if not isinstance(scope, str):
            raise DefinitionError(f"scope {scope!r} is not a string")
        if not scope.strip():
            raise DefinitionError("a scope must not be empty or whitespace")
    return scopes


@frozen_slots_dataclass
class ScopePolicy:
    """Require every declared scope to be granted to the active principal."""

    required_scopes: frozenset[str]

    def __init__(self, required_scopes: Iterable[str] = ()) -> None:
        object.__setattr__(
            self,
            "required_scopes",
            _normalize_scopes(required_scopes, "required scopes"),
        )

    async def evaluate(self, context: ExecutionContext) -> PolicyResult:
        principal = getattr(context, "principal", None)
        granted_scopes = getattr(principal, "scopes", frozenset())
        missing = sorted(self.required_scopes.difference(granted_scopes))
        if missing:
            return PolicyFailure(reason=f"missing required scopes: {', '.join(missing)}")
        return PolicySuccess()
