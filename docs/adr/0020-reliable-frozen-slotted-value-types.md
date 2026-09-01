# ADR 0020 — Reliable Frozen Slotted Value Types

- Status: Proposed
- Date: 2026-08-31
- Tracking: GitHub Issue #3

## Context

Agnara's core uses immutable value types so compiled state can be shared
without accidental mutation. `CapabilityId` and `CapabilityDefinition` are
standard-library dataclasses with `frozen=True, slots=True`.

On CPython 3.14.4, assigning or deleting an unknown attribute on that
combination raises a confusing `TypeError` from the generated method instead
of `dataclasses.FrozenInstanceError`. The slots transformation rebuilds the
class, but the generated `__setattr__` and `__delattr__` close over the
pre-transformation class.

Dropping slots avoids the error but gives every instance a dictionary. That
cost matters for the documented 10,000-capability startup scenario.

## Decision

Core frozen slotted dataclasses use the internal
`agnara._frozen.frozen_slots_dataclass` decorator.

The decorator delegates field/init/equality/hash/repr/slots generation to
`dataclasses.dataclass(frozen=True, slots=True)`, then replaces only the two
broken mutation guards. Assignment and deletion—whether for a declared or
unknown name—raise `FrozenInstanceError` with the standard clear form:

```text
cannot assign to field 'name'
cannot delete field 'name'
```

Construction and `__post_init__` normalization remain possible through
`object.__setattr__`, as with standard frozen dataclasses. The helper is
internal and does not enlarge Agnara's public API.

## Memory evidence

Option 2 from Issue #3 (drop slots) was measured with the reproducible
`benchmarks/frozen_value_type_memory.py` script. It compares 10,000 frozen
seven-field instances shaped like `CapabilityDefinition`, using the median of
five `tracemalloc` trials.

Recorded baseline:

```text
command: .venv\Scripts\python.exe benchmarks\frozen_value_type_memory.py
commit: 61d659e
platform: Windows 11 10.0.26200
processor: Intel64 Family 6 Model 140 Stepping 1, GenuineIntel
Python: CPython 3.14.4 (tags/v3.14.4:23116f9, Apr 7 2026 14:10:54)
count: 10,000
trials: 5
slotted current bytes: 965,672 (96.5672 per instance including holding list)
dict-backed current bytes: 1,365,672 (136.5672 per instance including holding list)
measured saving: 400,000 bytes (40 bytes per instance)
slotted fraction: 0.707103901961818
```

The decision requires the slotted form to use less measured memory than the
dict-backed form. It does not claim a universal percentage across Python
builds or platforms.

## Consequences

Positive:

- typos produce a clear, documented protocol-neutral exception;
- all current core frozen value types behave consistently;
- slots and their measured memory benefit remain;
- future types have one reviewed construction path.

Negative:

- Agnara carries a small compatibility shim around a CPython/dataclasses
  implementation defect;
- the helper must be revisited when the supported Python baseline fixes the
  generated methods;
- unusual user subclasses cannot rely on mutating inherited frozen instances,
  which matches the intended value semantics.

## Guardrails

- core code does not use raw `@dataclass(frozen=True, slots=True)` for new
  frozen value types;
- tests cover declared and unknown assignment plus unknown deletion;
- tests assert that every current public frozen value type remains slotted;
- the helper remains standard-library-only and transport-neutral;
- no benchmark result is generalized beyond its recorded environment.

## Revisit when

- the minimum supported CPython version produces `FrozenInstanceError` for
  unknown names with frozen slotted dataclasses;
- dataclasses adds an official hook that avoids method replacement;
- profiling shows the wrapper has a correctness or measurable construction
  cost.
