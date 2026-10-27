# ADR 0097 — HTTP OpenAPI complete-result output schemas

- Status: Proposed
- Tracking: GitHub Issue #674
- Related: ADR 0018, ADR 0032, ADR 0086 D5

## Context

ADR 0086 compiles and validates explicit capability output contracts, while
reserving their HTTP discovery projection for a separate decision. OpenAPI
still publishes an unconstrained success body even when the same plan rejects
a handler result that violates `output=...`.

## Decision

For an explicitly published, non-HEAD complete-result HTTP operation, use a
detached JSON-compatible copy of `plan.output_schema.json_schema()` as the
200 `application/json` schema. Use the same schema-port copy/validation
boundary already used for inputs. Neither handler return annotations nor a
second HTTP-specific output declaration define this contract.

The kernel's default `Any` contract remains unconstrained. The existing
200/204/default response vocabulary is retained: a non-None success is JSON
200, None is bodyless 204, and failures use the existing RFC 9457 mapping.
HEAD has no response content or output-schema retrieval. The projection
does not infer which statuses a particular handler can reach or rewrite
nullable/custom JSON Schema fragments. A nullable schema can therefore allow
null while actual None values still take the 204 branch; even a null-only
contract retains the generic status vocabulary. Schemas constrain represented
values, not the reachability of every admitted value/status pair.

SSE remains excluded. Its per-unit and terminal framing needs its own future
schema projection and cannot be described as a complete JSON response.

## Publication, validation and ownership

An absent OpenApiOperation withholds the entire operation. That filter runs
before output metadata is retrieved, just as it precedes input schemas and
descriptions. Publishing an operation deliberately publishes its compiled
input and output type descriptions. It grants no invocation authority.
No handler, provider or runtime dependency value is inspected or executed.

Custom schema adapters must return JSON-compatible mapping fragments for
published response bodies. Non-mapping roots, non-string keys, non-finite
numbers, cycles and non-JSON values fail through the existing HTTP definition
error boundary when OpenAPI is projected, including startup when a schema or
documentation surface is configured. Previously ignored invalid output metadata
is now checked for a published body operation; unpublished and HEAD-only
operations do not retrieve that metadata.

Copy fragments recursively so modifying the resulting document cannot mutate
a compiled schema or another document, and later source-fragment changes
cannot mutate an already projected document or precompiled served bytes.
JSON serialization stays deterministic. Core remains transport-neutral and
dependency-free.

## Alternatives and limits

Inferring output from a return annotation conflicts with ADR 0086. Adding an
HTTP response-model declaration duplicates the capability's contract. Keeping
all typed outputs generic loses an existing validated contract. Interpreting
arbitrary JSON Schema to narrow statuses or remove null would add a second
schema engine; preserving the existing status vocabulary is the reversible
choice for this first projection.

This proposal changes generated discovery for declared outputs, not runtime
validation, serialization or public syntax. It does not adopt MCP outputSchema,
streaming schemas, new UI compatibility or complete OpenAPI conformance.
Maintainer review remains pending; the record is not promoted to Accepted.
