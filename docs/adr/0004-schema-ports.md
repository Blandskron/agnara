# ADR 0004 — Schema Libraries Behind Ports

- Status: Proposed

## Decision

Agnara core will not require Pydantic or msgspec.

It defines schema/validation interfaces and allows adapters.

## Rationale

A framework intended to outlive current libraries should not make a third-party validation implementation part of its conceptual architecture.

## Open question

Which adapter, if any, becomes the recommended default after benchmarks and ergonomics experiments?
