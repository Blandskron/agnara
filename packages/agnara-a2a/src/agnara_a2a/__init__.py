"""Agent-to-Agent exposure adapter for Agnara capabilities.

Owns Agent Card and skill projection, A2A tasks, streaming, protocol
bindings and A2A security/version mapping.

Depends on ``agnara-core``. Must not import a sibling adapter.
See ``ARCHITECTURE.md`` sections 3 and 4, and Post-v0.1 in ``BACKLOG.md``.
"""

#: Reserved namespace: this distribution holds the package boundary and the
#: dependency direction for A2A while the adapter itself is Post-v0.1 work.
#: The empty public surface is declared, not accidental.
__all__: list[str] = []
