import math
from typing import Any

from agnara._frozen import frozen_slots_dataclass
from agnara.capability.identity import CapabilityId
from agnara.errors import DefinitionError

__all__ = ["Invocation"]


@frozen_slots_dataclass
class Invocation:
    """A protocol-neutral request to execute a capability.

    Represents what the caller asked to do, not how it arrived (HTTP, MCP, etc).
    Carries the unvalidated payload from the transport.
    """

    capability_id: CapabilityId
    payload: dict[str, Any]
    metadata: dict[str, Any]
    deadline: float | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.capability_id, CapabilityId):
            raise DefinitionError(
                f"capability_id must be a CapabilityId, got {type(self.capability_id).__name__}; "
                "use CapabilityId.parse() to build one from a string"
            )
        if not isinstance(self.payload, dict):
            raise DefinitionError("payload must be a dictionary")
        if not isinstance(self.metadata, dict):
            raise DefinitionError("metadata must be a dictionary")
        if self.deadline is not None and (
            isinstance(self.deadline, bool)
            or not isinstance(self.deadline, int | float)
            or not math.isfinite(self.deadline)
        ):
            raise DefinitionError("deadline must be a finite monotonic timestamp or None")
        if self.deadline is not None:
            object.__setattr__(self, "deadline", float(self.deadline))
