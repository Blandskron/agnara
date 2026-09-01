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
