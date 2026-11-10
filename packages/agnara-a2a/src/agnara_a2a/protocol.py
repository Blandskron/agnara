"""Exact A2A protocol and SDK identities this adapter is tested against (ADR 0010)."""

from __future__ import annotations

__all__: list[str] = []

#: The A2A protocol revision this adapter serves, compared as exact ``Major.Minor``.
A2A_PROTOCOL_VERSION = "1.0"

#: Every revision the admission gate accepts (ADR 0098 D1). Adding one needs a
#: reviewed record and its own tests.
SUPPORTED_A2A_PROTOCOL_VERSIONS: tuple[str, ...] = (A2A_PROTOCOL_VERSION,)

#: The official ``a2a-sdk`` release pinned by ``agnara-a2a``. The ADR 0098 D7
#: nesting ceilings are measured properties of this pin.
A2A_PYTHON_SDK_VERSION = "1.3.0"
