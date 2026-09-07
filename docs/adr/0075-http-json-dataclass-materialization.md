# ADR 0075 — HTTP JSON Dataclass Materialization

- Status: Proposed
- Date: 2026-09-07
- Tracking: GitHub Issue #296

## Context

The standard schema adapter correctly projects a dataclass as a JSON object but
strictly accepts only an existing dataclass instance. HTTP JSON decoding
produces dictionaries, so every request matching the published schema failed
before its capability ran.

ADR 0025 deliberately keeps direct core invocation strict and assigns
wire-format conversion to the transport that understands that format.

## Decision

An HTTP `BODY` binding materializes JSON-only representations into the types
described by the compiled standard schemas before invoking the shared core
validation path:

- JSON objects become declared dataclass instances recursively;
- JSON arrays become declared tuples recursively;
- JSON scalar values become declared standard-library Enum members;
- nested lists, dictionaries and unions propagate the same conversion.

Unknown custom `TypeSchema` implementations receive decoded JSON unchanged and
retain control of validation/coercion. The standard core adapter is unchanged:
direct invocation still requires exact Python types.

Unknown dataclass fields and missing required fields fail at the HTTP boundary.
Omitted default/default-factory fields are left to the dataclass constructor.

## Consequences

- The accepted request now agrees with the generated OpenAPI schema.
- HTTP capabilities can use ordinary standard-library dataclasses without a
  dictionary workaround.
- MCP and direct invocation semantics do not change.
- Dataclass construction may run `__post_init__`; expected `TypeError` or
  `ValueError` failures become a redacted binding failure, while unexpected
  exceptions remain internal failures rather than being disguised as input.

## Threat analysis

The materializer uses the already compiled immutable schema graph and performs
no reflection on request-selected types. It rejects surplus keys before object
construction, never imports a type named by JSON, preserves the existing body
and multipart limits, and does not include constructor exception text in the
client response. Recursive schema graphs are already rejected at compilation.
