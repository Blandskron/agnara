# msgspec schema adapter prototype

This executable prototype answers backlog item E2.5 without adding a product
distribution or changing Agnara's seven-package dependency graph. It targets
`msgspec` 0.21 and implements the existing schema port structurally; it does
not inherit an Agnara adapter base class.

## Observed fit

- `msgspec.convert(..., strict=True)` validates builtin Python values and can
  construct `Struct` and dataclass instances.
- `msgspec.json.schema()` rejects unsupported annotations during compilation
  and emits plain JSON Schema 2020-12/OpenAPI 3.1-compatible data.
- `Struct`, dataclass, collection, union and `Annotated[..., Meta(...)]`
  schemas fit the current port without changing core.
- Compiled schema documents are stored as immutable bytes and decoded to a
  fresh mapping for each caller.

## Limitations to carry into E2.7

- `msgspec.convert` has no reusable public converter object analogous to its
  JSON `Decoder`. The prototype compiles support and JSON Schema at startup,
  but E2.7 must measure whether repeated conversion reparses annotations or
  otherwise affects the invocation hot path.
- `ValidationError` exposes its location only through formatted text in
  msgspec 0.21. The prototype translates unambiguous struct fields and list
  indices. Arbitrary dictionary keys appear as `[...]`, so their provider
  location remains in the message and the Agnara path stays empty.
- Strict conversion is not identity-only validation: builtin mappings can
  become `Struct`/dataclass instances and lists can become tuples or sets.
- No recommendation, default selection or performance claim is made here;
  those belong to E2.7 after the Pydantic prototype in E2.6.

Run the focused evidence with:

```console
uv run pytest tests/experiments/test_msgspec_schema_adapter.py
```
