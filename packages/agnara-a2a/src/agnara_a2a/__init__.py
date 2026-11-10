"""Agent-to-Agent (A2A) exposure adapter for Agnara capabilities.

Serves the ADR 0098 complete-result profile: one capability per surface,
JSON-RPC 2.0 at protocol revision 1.0, one immediate ``Message`` per
``SendMessage`` and no tasks, streaming or push notifications. Every export is
``provisional`` (ADR 0099) until the A2A-04b evidence is reviewed.

Depends on ``agnara`` and the pinned official ``a2a-sdk``. Must not import a
sibling adapter. See ``ARCHITECTURE.md`` for boundaries and
``docs/MATURITY.md`` for status.
"""

from .card import A2aAgentCard
from .exposure import A2a, A2aDefinitionError, A2aSkillExposure
from .protocol import (
    A2A_PROTOCOL_VERSION,
    A2A_PYTHON_SDK_VERSION,
    SUPPORTED_A2A_PROTOCOL_VERSIONS,
)
from .server import build_a2a_app

__all__ = [
    "A2A_PROTOCOL_VERSION",
    "A2A_PYTHON_SDK_VERSION",
    "SUPPORTED_A2A_PROTOCOL_VERSIONS",
    "A2a",
    "A2aAgentCard",
    "A2aDefinitionError",
    "A2aSkillExposure",
    "build_a2a_app",
]
