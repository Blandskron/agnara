"""Runtime-owned execution identity (ADR 0087).

This is deliberately private.  An execution identifier is an opaque value
carried by the existing execution objects; it is not a transport field or a
new persistence/idempotency API.
"""

from __future__ import annotations

import re
from uuid import uuid4

from agnara._frozen import frozen_slots_dataclass
from agnara.errors import DefinitionError

__all__: list[str] = []

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]*\Z")


@frozen_slots_dataclass
class ExecutionId:
    """A validated opaque identity for one logical execution.

    The generated representation is a UUID4 hexadecimal token, providing the
    at-least-128-bit randomness ADR 0087 requires.  The constructor keeps the
    token grammar private so the existing result and telemetry value objects
    can defend their invariant without creating a caller-controlled boundary.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _TOKEN.fullmatch(self.value):
            raise DefinitionError(
                "execution_id must be a non-empty ASCII opaque token containing only "
                "letters, digits, '.', '_', '~', or '-'"
            )

    @classmethod
    def generate(cls) -> ExecutionId:
        return cls(uuid4().hex)

    def __str__(self) -> str:
        return self.value
