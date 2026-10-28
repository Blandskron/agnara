"""Reserved event adapter namespace; no runtime implementation.

No event publication, broker integration or AsyncAPI projection is implemented
here. The distribution depends on ``agnara`` and must not import sibling
adapters. See ``docs/MATURITY.md`` for status and ``ARCHITECTURE.md`` for
boundaries; future broker-specific code belongs in separate adapters.
"""

#: Reserved namespace: this distribution holds the package boundary and the
#: dependency direction while the event adapter remains unimplemented.
#: The empty public surface is declared, not accidental.
__all__: list[str] = []
