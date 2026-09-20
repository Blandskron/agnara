"""Schema round trips and dependency-graph compilation as algebra.

`QUALITY_GATES.md` names schema round trips and dependency DAGs as
property-test targets, and both are combinatorial for the same reason: they
compose. A schema is built from nested schemas, and a provider graph is built
from providers that require other providers, so the number of shapes grows
faster than anyone will enumerate by hand.

The invariant for a round trip is that it loses nothing:

    materialize(schema, serialize(value)) == value

and the invariant for validation is that it is total -- one accepted value or
one typed `ValidationError`, never an `AttributeError`, a `RecursionError` or
a silently repaired value.
"""

from __future__ import annotations

import string
from dataclasses import dataclass
from typing import Any

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from agnara.core.di import DIRegistry, provider
from agnara.errors import SchemaError, ValidationError
from agnara.schema import StandardSchemaAdapter, materialize_json, serialize_json

ADAPTER = StandardSchemaAdapter()


@dataclass(frozen=True)
class Item:
    quantity: int
    label: str


@dataclass(frozen=True)
class Order:
    reference: str
    items: list[Item]
    note: str | None


names = st.text(alphabet=string.ascii_letters, min_size=1, max_size=8)

items = st.builds(
    Item,
    quantity=st.integers(min_value=-1000, max_value=1000),
    label=st.text(max_size=16),
)
orders = st.builds(
    Order,
    reference=names,
    items=st.lists(items, max_size=4),
    note=st.one_of(st.none(), st.text(max_size=16)),
)

#: Values the JSON contract is expected to carry unchanged.
json_values = st.recursive(
    st.one_of(
        st.none(),
        st.booleans(),
        st.integers(min_value=-(2**53), max_value=2**53),
        st.text(max_size=16),
    ),
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(st.text(max_size=8), children, max_size=4),
    ),
    max_leaves=10,
)


# ---------------------------------------------------------------------------
# Round trips
# ---------------------------------------------------------------------------


@given(order=orders)
def test_a_dataclass_survives_a_json_round_trip(order: Order) -> None:
    """Serialize then materialize must be the identity on declared shapes."""
    schema = ADAPTER.compile(Order)

    restored = materialize_json(schema, serialize_json(order))

    assert restored == order
    assert schema.validate(restored) == order


@given(order=orders)
def test_a_round_trip_is_idempotent(order: Order) -> None:
    """Going round twice must not drift from going round once."""
    schema = ADAPTER.compile(Order)

    once = materialize_json(schema, serialize_json(order))
    twice = materialize_json(schema, serialize_json(once))

    assert once == twice
    assert serialize_json(once) == serialize_json(twice)


@given(value=json_values)
def test_serialization_of_plain_json_is_a_fixed_point(value: object) -> None:
    """Values already in the JSON contract pass through unchanged."""
    assert serialize_json(value) == value


@given(
    quantity=st.integers(min_value=-1000, max_value=1000),
    label=st.text(max_size=16),
)
def test_a_materialized_value_is_a_real_instance_not_a_mapping(quantity: int, label: str) -> None:
    schema = ADAPTER.compile(Item)

    materialized = materialize_json(schema, {"quantity": quantity, "label": label})

    assert isinstance(materialized, Item)
    assert materialized == Item(quantity=quantity, label=label)


# ---------------------------------------------------------------------------
# Validation is total
# ---------------------------------------------------------------------------


@given(value=json_values)
# Shapes a dataclass schema must refuse rather than coerce or crash on.
@example(value=None)
@example(value=[])
@example(value={})
@example(value={"quantity": "1", "label": "x"})
@example(value={"quantity": 1})
@example(value={"quantity": 1, "label": "x", "unexpected": True})
def test_validating_arbitrary_json_either_returns_a_value_or_raises_validation_error(
    value: object,
) -> None:
    """One accepted value or one typed refusal. Nothing else escapes.

    Validation is the boundary that decides, not materialization:
    `materialize_json` performs the declared wire conversion and passes an
    undeclared shape through unchanged, so `validate` is what must be total.
    """
    schema = ADAPTER.compile(Item)

    try:
        validated = schema.validate(materialize_json(schema, value))
    except ValidationError as error:
        assert isinstance(error.path, tuple)
        return
    assert isinstance(validated, Item)


@given(depth=st.integers(min_value=1, max_value=200))
def test_deeply_nested_input_is_refused_without_exhausting_the_stack(depth: int) -> None:
    """A nested value the schema does not declare is a refusal, not a crash."""
    schema = ADAPTER.compile(Item)
    nested: Any = "leaf"
    for _ in range(depth):
        nested = [nested]

    with pytest.raises(ValidationError):
        schema.validate(materialize_json(schema, {"quantity": nested, "label": "x"}))


@given(value=json_values)
def test_a_validated_value_always_validates_again(value: object) -> None:
    """Validation is idempotent, so a revalidated value cannot drift."""
    schema = ADAPTER.compile(Item)

    try:
        once = schema.validate(materialize_json(schema, value))
    except ValidationError:
        return
    assert schema.validate(once) == once


def test_an_undeclarable_annotation_is_a_schema_error_not_a_surprise() -> None:
    """Compilation refuses what it cannot describe, before anything runs."""

    class Opaque:
        def __init__(self, handle: object) -> None:
            self.handle = handle

    with pytest.raises(SchemaError):
        ADAPTER.compile(Opaque)


# ---------------------------------------------------------------------------
# Dependency graphs
# ---------------------------------------------------------------------------


def _provider_for(bound: type, needs: type | None) -> Any:
    """Build a provider whose annotations are real classes, not strings.

    This module uses `from __future__ import annotations`, so an annotation
    written in source is a string that `get_type_hints` resolves in the module
    namespace -- where a class created inside a test does not exist. Assigning
    `__annotations__` directly hands the compiler the actual objects.
    """

    def make(*args: Any, **kwargs: Any) -> Any:
        return bound()

    if needs is None:
        make.__annotations__ = {"return": bound}
    else:
        make.__annotations__ = {"upstream": needs, "return": bound}
    make.__name__ = f"provide_{bound.__name__}"
    return provider()(make)


def _capability_requiring(kind: type) -> Any:
    def capability(*args: Any, **kwargs: Any) -> None:
        return None

    capability.__annotations__ = {"dependency": kind, "return": None}
    return capability


@given(length=st.integers(min_value=1, max_value=6))
def test_a_provider_chain_resolves_at_any_supported_depth(length: int) -> None:
    """A linear chain of any supported length compiles to one ordered DAG."""
    from agnara.core.di.compiler import compile_dag

    registry = DIRegistry()
    kinds: list[type] = []
    previous: type | None = None

    for index in range(length):
        kind = type(f"Value{index}", (), {})
        registry.bind(kind, _provider_for(kind, previous))
        kinds.append(kind)
        previous = kind

    capability = _capability_requiring(kinds[-1])
    resolved = compile_dag(registry, [capability])

    assert capability in resolved
    assert kinds[-1] in resolved[capability]


@given(size=st.integers(min_value=2, max_value=6))
def test_a_dependency_cycle_of_any_length_is_refused_not_hung(size: int) -> None:
    """A cycle terminates with a typed error rather than recursing forever."""
    from agnara.core.di.compiler import DependencyCycleError, compile_dag

    kinds = [type(f"Node{index}", (), {}) for index in range(size)]
    registry = DIRegistry()
    for index, kind in enumerate(kinds):
        registry.bind(kind, _provider_for(kind, kinds[(index + 1) % size]))

    with pytest.raises(DependencyCycleError):
        compile_dag(registry, [_capability_requiring(kinds[0])])


@given(size=st.integers(min_value=2, max_value=6))
def test_a_shared_dependency_is_resolved_once_per_graph(size: int) -> None:
    """A diamond is a DAG, not a cycle: sharing a provider must be allowed."""
    from agnara.core.di.compiler import compile_dag

    shared = type("Shared", (), {})
    registry = DIRegistry()
    registry.bind(shared, _provider_for(shared, None))

    leaves = [type(f"Leaf{index}", (), {}) for index in range(size)]
    for leaf in leaves:
        registry.bind(leaf, _provider_for(leaf, shared))

    resolved = compile_dag(registry, [_capability_requiring(leaf) for leaf in leaves])

    assert len(resolved) == size
    for capability, dependencies in resolved.items():
        assert any(leaf in dependencies for leaf in leaves), capability
