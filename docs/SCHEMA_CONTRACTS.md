# Python input contracts and explicit JSON boundaries

Version boundary: this guide includes JSON enum and numeric validation fixes
recorded under `CHANGELOG.md` `[Unreleased]`. Those edge-case corrections are
not present in published 1.0.3. For a baseline dataclass example, use
[http_service.py](../examples/http_service.py). Public imports are unchanged.

Run the complete standard-library example from a synchronized checkout:

```bash
uv sync
uv run python examples/schema_contracts.py
```

[examples/schema_contracts.py](../examples/schema_contracts.py) defines nested
dataclasses and an enum, compiles their schemas once and invokes plans directly.
It requires no HTTP/MCP server or third-party model library. The local principal
is a trusted fixture, not an authentication implementation.

Expected standard output:

```text
denied: forbidden
direct: {"currency": "CLP", "total_cents": 250}
mapping: invalid_input
json: {"currency": "CLP", "total_cents": 250}
json_defaults: {"currency": "CLP", "total_cents": 250}
bad_quantity: invalid_input
bool_quantity: invalid_input
extra_field: invalid_input
bad_currency: invalid_input
bad_output: internal_failure
annotation_only: "annotation alone is unconstrained"
events: ['quote.enter', 'quote.enter', 'quote.enter', 'broken.enter', 'annotated.enter']
```

The deliberate output violation also produces a redacted operator log on
standard error. Private fixture values never appear in the displayed failures.

## Strict Python values are the direct contract

`quote(order: Order)` accepts an `Order` whose `lines` hold `Line` instances,
whose quantities/prices are integers and whose currency is a `Currency` member.
The standard adapter validates the declared structure, including nested fields.
The direct call receives its original dataclass object; a mapping with matching
field names is still a different Python type and is rejected.

Dataclasses do not enforce annotations when they are constructed. Agnara's
compiled schema validates them at invocation, rather than assuming an existing
object is valid. Primitive validation is strict: strings containing digits do
not become integers, and `True` is not accepted for an integer field. The
standard dataclass schema also requires the exact declared dataclass class,
rather than accepting a subclass with extra fields.

The demo's integers describe types, not business rules. Negative quantities,
currency-dependent pricing rules and authorization to commit a purchase need
explicit application validation/policy. A schema does not supply those rules.

## Materialize decoded JSON explicitly

JSON has objects, arrays and scalar values, but no dataclass instances or enum
members. At that boundary the application explicitly selects conversion:

```python
from agnara.execution import invoke_result
from agnara.schema import materialize_json

outcome = await invoke_result(plan, context, input_materializer=materialize_json)
```

Here `plan` and `context` are application-owned objects as in the full example.
The payload is already decoded JSON data; `materialize_json` does not parse raw
JSON text. Conversion follows policy evaluation and precedes strict validation.
The denied call in this guide never reaches conversion or handler work.

The compiled schema guides recursive conversion of object fields to dataclasses
and enum values to members. A wire currency `"CLP"` becomes `Currency.CLP`;
`"undeclared currency"` remains invalid. Nested scalar values still undergo
strict validation: conversion does not repair a string quantity or boolean.
Unknown object fields are rejected, rather than silently discarded.

An omitted field with a dataclass default uses that constructor default. The
`json_defaults` call omits currency and note and receives `Currency.CLP` and
`None`. Required fields remain required. Constructors and default factories
can run during materialization; use application value types without external
side effects because input conversion is not handler authorization to perform
business effects. The original wire fixture remains unchanged.

The demo retains `plan.input_schemas["order"].json_schema()` for inspection:
`lines` is required, currency/note have defaults, currency publishes its two
declared values and objects forbid additional properties. Schema projections
describe the type contract; they do not grant permission to publish sensitive
names or model metadata automatically.

Input failure paths identify structure without including the rejected value.
For example a quantity error has canonical details
`("order", "lines", 0, "quantity")`. The guide prints only failure codes;
applications choose which safe details to expose at their protocol boundary.

## Declare output separately from return annotations

The successful handler uses `@app.capability(output=Receipt, ...)`. Its returned
`Receipt` is validated before the caller receives `Success`. A wrong output
field is a producer contract violation: `bad_output` becomes redacted
`FailureCode.INTERNAL_FAILURE`, with no private value or output-schema
diagnostic. Invalid caller input instead produces `FailureCode.INVALID_INPUT`.

The intentionally broken handler uses a cast to construct an invalid receipt
as a fault fixture. This is demonstration code, not a way to bypass runtime
validation. Its handler has already run when output validation fails; output
validation cannot roll back effects. Applications own transactional semantics.

`annotated_only() -> int` deliberately returns a string using a cast, but does
not declare `output=...`. Its compiled output is the intentional unconstrained
`Any` contract, projected as `{}`, and the string is successful. Return
annotations do not silently define capability output. Declare `output=...`
when the runtime must enforce it. Streaming uses that same explicit declaration
for each yielded unit; this guide covers complete results only.

## Project successful values to JSON

Direct callers retain Python `Receipt` and `Currency` values. At an explicit
JSON boundary, `serialize_json(result.value)` converts the successful dataclass
to an object and its enum member to a string. The guide then calls `json.dumps`
with sorted keys for reproducible display. It does not serialize the canonical
outcome object itself or assume `Success` is a wire document.

Serialization and output validation are separate operations. Even an
unconstrained output must be representable as JSON if the caller chooses a
JSON boundary; unsupported objects, cyclic structures, non-finite floats and
non-string mapping keys can fail serialization. Adapters own how to map that
error safely. This guide adds no transport projection or conformance claim.

The core schema port remains replaceable. The standard adapter is the shipped
implementation; Pydantic/msgspec adapters remain experiments. The helper's
conversions apply to standard schemas; an unknown custom schema receives its
input unchanged, so a custom adapter must define its own boundary behavior.

## Evidence and ownership

[Guide tests](../tests/docs/test_schema_contracts_example.py) check equivalent
Python/JSON outputs, direct identity and detached JSON objects, defaults,
policy-before-materialization order, error paths, enum/boolean/extra-field
refusal, output redaction, the unconstrained annotation case, container closure,
cancellation propagation and bounded outside-checkout execution. The handler
event list confirms invalid inputs never enter it. Fixtures belong to one
demonstration/event loop, create no background work and close the application
container in `finally`; a separate five-second watchdog bounds the demo.
Existing [standard schema tests](../tests/unit/test_standard_schema_adapter.py)
and [dataclass tests](../tests/unit/test_dataclass_schema_adapter.py) provide the
broader type-contract evidence. No runtime/API/dependency changes are made.
