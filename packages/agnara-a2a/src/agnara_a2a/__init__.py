"""Reserved Agent-to-Agent adapter namespace; no runtime implementation.

No Agent Card, task, streaming or protocol API is implemented here. The
distribution depends on ``agnara`` and must not import sibling adapters.
See ``docs/MATURITY.md`` for status and ``ARCHITECTURE.md`` for boundaries.
"""

#: Reserved namespace: this distribution holds the package boundary and the
#: dependency direction while the A2A adapter remains unimplemented.
#: The empty public surface is declared, not accidental.
__all__: list[str] = []
