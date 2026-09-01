# Pydantic schema adapter prototype

This executable prototype answers backlog item E2.6 without adding a product
distribution or changing Agnara's seven-package dependency graph. It targets
pydantic 2.9+ and implements the existing schema port structurally; it does
not inherit an Agnara adapter base class.

## Observed fit

- pydantic.TypeAdapter validates builtin Python values and can
  construct BaseModel instances in strict mode.
- TypeAdapter(annotation).json_schema() rejects unsupported annotations during compilation
  and emits plain JSON Schema.
- BaseModel, dataclass, collection, union and Annotated[..., Field(...)]
  schemas fit the current port without changing core.
- Compiled schema documents are generated on demand as mappings.

## Limitations to carry into E2.7

- In strict mode, Pydantic refuses to construct pure Python dataclasses from dictionaries (Input should be an instance of Point), unlike its behavior with BaseModel or msgspec's behavior with Struct and dataclasses.
- Pydantic's ValidationError provides an exact tuple loc field, making unambiguous paths natively accessible, including dictionary keys. The prototype translates this perfectly to Agnara's ValidationError.path.
- When multiple errors occur, Pydantic collects them in a list. The prototype returns only the first error to keep the Agnara ValidationError shape simple.
- No recommendation, default selection or performance claim is made here;
  those belong to E2.7.

Run the focused evidence with:

`console
uv run pytest tests/experiments/test_pydantic_schema_adapter.py
`
