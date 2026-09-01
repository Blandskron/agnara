"""Project introspection and scaffolding CLI for Agnara.

Owns ``agnara project create``, ``agnara app create``, capability
generation, introspection commands and diagnostics. Templates live here,
never in ``agnara-core``.

Depends on ``agnara-core``. Must not import a sibling adapter.
See ``ARCHITECTURE.md`` section 15, ``docs/CLI_SPEC.md`` and EPIC 0A.
"""
