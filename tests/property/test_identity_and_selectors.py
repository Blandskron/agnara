"""Identity and selector normalization, as algebra rather than examples.

Two normalizers decide who and what a stored or audited fact belongs to:
`CapabilityId`, which names a capability in policy rules and audit logs, and
`IdempotencyScope`, which decides whether two requests are the same request.
A normalizer that loses information silently merges things that should stay
apart, which is why these are written as round trips and injectivity rather
than as a list of accepted spellings.
"""

from __future__ import annotations

import string

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from agnara.capability import CapabilityId
from agnara.errors import DefinitionError
from agnara.execution import IdempotencyScope

#: Constructed rather than filtered. Filtering arbitrary text for
#: `str.isidentifier` rejects most draws and made this lane cost seconds.
identifiers = st.builds(
    lambda head, tail: head + tail,
    st.text(alphabet=string.ascii_letters + "_", min_size=1, max_size=1),
    st.text(alphabet=string.ascii_letters + string.digits + "_", max_size=7),
)

#: The grammar `_KEY` accepts: an alphanumeric head, then unreserved characters.
key_tail = string.ascii_letters + string.digits + "._~-"
idempotency_keys = st.builds(
    lambda head, tail: head + tail,
    st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=1),
    st.text(alphabet=key_tail, max_size=24),
)
principals = st.text(min_size=1, max_size=32).filter(lambda value: value.strip() != "")


# ---------------------------------------------------------------------------
# CapabilityId
# ---------------------------------------------------------------------------


@given(namespace=identifiers, name=st.lists(identifiers, min_size=1, max_size=3))
def test_a_capability_id_survives_a_string_round_trip(namespace: str, name: list[str]) -> None:
    """`parse(str(id)) == id` is what makes an id safe to log and re-read."""
    original = CapabilityId(namespace=namespace, name=".".join(name))

    assert CapabilityId.parse(str(original)) == original
    assert str(CapabilityId.parse(str(original))) == str(original)


@given(namespace=identifiers, name=st.lists(identifiers, min_size=2, max_size=4))
def test_only_the_first_separator_splits_a_dotted_name(namespace: str, name: list[str]) -> None:
    """A dotted qualified name stays inside `name`, so nothing is ambiguous."""
    parsed = CapabilityId.parse(f"{namespace}.{'.'.join(name)}")

    assert parsed.namespace == namespace
    assert parsed.name == ".".join(name)


@given(text=st.text(max_size=40))
# Shapes the separator rules must each reject rather than mangle.
@example(text="")
@example(text=".")
@example(text="a.")
@example(text=".a")
@example(text="a..b")
@example(text="a.b.")
@example(text="commerce.payments.refund")
@example(text="a b.c")
@example(text="\x00.\x00")
def test_parsing_arbitrary_text_either_round_trips_or_is_a_definition_error(
    text: str,
) -> None:
    """The parser is total: one accepted value, or one typed refusal.

    Anything else -- an `AttributeError`, an `IndexError`, a silently repaired
    id -- would mean a caller cannot tell a real capability from a malformed
    name it happened to survive.
    """
    try:
        parsed = CapabilityId.parse(text)
    except DefinitionError:
        return
    # Whatever was accepted must be exactly what it prints as.
    assert str(parsed) == text
    assert CapabilityId.parse(str(parsed)) == parsed


@given(
    first=st.tuples(identifiers, identifiers),
    second=st.tuples(identifiers, identifiers),
)
def test_distinct_identities_never_collapse_to_one_string(
    first: tuple[str, str], second: tuple[str, str]
) -> None:
    """Equality of the printed form must imply equality of the parts."""
    left = CapabilityId(namespace=first[0], name=first[1])
    right = CapabilityId(namespace=second[0], name=second[1])

    assert (str(left) == str(right)) == (left == right)
    if left == right:
        assert hash(left) == hash(right)


# ---------------------------------------------------------------------------
# Idempotency selectors
# ---------------------------------------------------------------------------


@given(
    capability=st.builds(CapabilityId, namespace=identifiers, name=identifiers),
    principal=principals,
    key=idempotency_keys,
    fingerprint=st.binary(min_size=1, max_size=32),
)
def test_a_valid_selector_keeps_every_part_it_was_given(
    capability: CapabilityId, principal: str, key: str, fingerprint: bytes
) -> None:
    scope = IdempotencyScope(
        capability_id=capability, principal_id=principal, key=key, fingerprint=fingerprint
    )

    assert scope.capability_id == capability
    assert scope.principal_id == principal
    assert scope.key == key
    assert scope.fingerprint == fingerprint


@given(
    capability=st.builds(CapabilityId, namespace=identifiers, name=identifiers),
    left=st.tuples(principals, idempotency_keys),
    right=st.tuples(principals, idempotency_keys),
    fingerprint=st.binary(min_size=1, max_size=16),
)
# The classic delimiter collision: a flat "principal:key" storage key would
# make these two selectors the same, letting one caller read the other's
# stored result. The selector is a tuple, so they stay distinct.
@example(
    capability=CapabilityId(namespace="billing", name="charge"),
    left=("alice:x", "y"),
    right=("alice", "x-y"),
    fingerprint=b"f",
)
def test_two_selectors_collide_only_when_every_part_matches(
    capability: CapabilityId,
    left: tuple[str, str],
    right: tuple[str, str],
    fingerprint: bytes,
) -> None:
    from agnara.execution.idempotency import _selector

    first = IdempotencyScope(
        capability_id=capability, principal_id=left[0], key=left[1], fingerprint=fingerprint
    )
    second = IdempotencyScope(
        capability_id=capability, principal_id=right[0], key=right[1], fingerprint=fingerprint
    )

    assert (_selector(first) == _selector(second)) == (left == right)


@given(
    capability=st.builds(CapabilityId, namespace=identifiers, name=identifiers),
    key=st.text(max_size=24),
    fingerprint=st.binary(max_size=8),
)
# Shapes the key grammar and the bounds must refuse rather than truncate.
@example(capability=CapabilityId("a", "b"), key="", fingerprint=b"f")
@example(capability=CapabilityId("a", "b"), key="-leading", fingerprint=b"f")
@example(capability=CapabilityId("a", "b"), key="has space", fingerprint=b"f")
@example(capability=CapabilityId("a", "b"), key="sl/ash", fingerprint=b"f")
@example(capability=CapabilityId("a", "b"), key="ok", fingerprint=b"")
def test_a_malformed_selector_is_refused_and_never_repaired(
    capability: CapabilityId, key: str, fingerprint: bytes
) -> None:
    """A rejected selector must raise, not get normalized into a valid one."""
    try:
        scope = IdempotencyScope(
            capability_id=capability, principal_id="actor", key=key, fingerprint=fingerprint
        )
    except DefinitionError:
        return
    assert scope.key == key
    assert scope.fingerprint == fingerprint


@given(over=st.integers(min_value=1, max_value=16))
def test_selector_bounds_are_enforced_at_the_edge(over: int) -> None:
    """The documented ceilings hold exactly, so a store cannot be flooded."""
    capability = CapabilityId("billing", "charge")

    IdempotencyScope(
        capability_id=capability, principal_id="a" * 256, key="k" * 128, fingerprint=b"f" * 64
    )
    with pytest.raises(DefinitionError, match="principal_id must not exceed"):
        IdempotencyScope(
            capability_id=capability,
            principal_id="a" * (256 + over),
            key="k",
            fingerprint=b"f",
        )
    with pytest.raises(DefinitionError, match="key must not exceed"):
        IdempotencyScope(
            capability_id=capability,
            principal_id="a",
            key="k" * (128 + over),
            fingerprint=b"f",
        )
    with pytest.raises(DefinitionError, match="fingerprint must not exceed"):
        IdempotencyScope(
            capability_id=capability,
            principal_id="a",
            key="k",
            fingerprint=b"f" * (64 + over),
        )


@given(
    capability=st.builds(CapabilityId, namespace=identifiers, name=identifiers),
    secret=st.text(alphabet=string.ascii_lowercase, min_size=4, max_size=12),
)
def test_a_selector_never_discloses_its_key_or_fingerprint_in_repr(
    capability: CapabilityId, secret: str
) -> None:
    """A routine diagnostic must not leak the caller's selector material.

    The generated part is wrapped in a marker no capability id can contain, so
    a hit is real disclosure rather than a short value coinciding with the
    namespace -- which is what made the first version of this test flap.
    """
    marker = f"zz{secret}zz"
    scope = IdempotencyScope(
        capability_id=capability,
        principal_id=f"principal-{marker}",
        key=f"key{marker}",
        fingerprint=marker.encode(),
    )

    rendered = repr(scope)
    assert marker not in rendered
    # The capability is deliberately still there: correlating a diagnostic to
    # a capability is the point, and its id is not caller-supplied material.
    assert repr(capability) in rendered
