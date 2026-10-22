"""Bounded regressions for vulnerable contributor dependency behavior."""

import gc
import hashlib
import operator
import ssl
import sys

import certifi
import pytest
from multidict import CIMultiDict, CIMultiDictProxy, MultiDict, MultiDictProxy


def test_certifi_excludes_compromised_root_and_preserves_trust() -> None:
    context = ssl.create_default_context(cafile=certifi.where())
    fingerprints = {
        hashlib.sha256(certificate).hexdigest()
        for certificate in context.get_ca_certs(binary_form=True)
    }
    # GHSA-6q48-6c7w-9gw2: emSign ECC Root CA - G3 must no longer be trusted.
    assert "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b" not in fingerprints
    # The unaffected emSign G1 and ISRG X1 roots must remain available.
    assert "40f6af0346a99aa1cd1d555a4e9cce62c7f9634603ee406615833dc8c8d00367" in fingerprints
    assert "96bcec06264976f37460779acf28c5a7cfe8a3c0aae11a8ffcee05c0bddf08c6" in fingerprints
    assert context.check_hostname
    assert context.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.parametrize("kind", ["multi", "ci", "multi_proxy", "ci_proxy"])
@pytest.mark.parametrize("operation", ["reflected_union", "subtraction", "intersection", "union"])
def test_multidict_items_operations_release_operand_references(kind: str, operation: str) -> None:
    if sys.implementation.name != "cpython" or MultiDict.__module__ != "multidict._multidict":
        pytest.skip("The affected C extension requires CPython and an available extension wheel")

    mapping = (
        CIMultiDict({"seed": "control"})
        if kind.startswith("ci")
        else MultiDict({"seed": "control"})
    )
    if kind == "multi_proxy":
        view = MultiDictProxy(mapping).items()
    elif kind == "ci_proxy":
        view = CIMultiDictProxy(mapping).items()
    else:
        view = mapping.items()

    sentinel = object()
    operand = [(f"key-{index}", sentinel) for index in range(8)]
    gc.collect()
    before = sys.getrefcount(sentinel)
    if operation == "reflected_union":
        result = operator.or_(operand, view)
    elif operation == "subtraction":
        result = operator.sub(view, operand)
    elif operation == "intersection":
        result = operator.and_(view, operand)
    else:
        result = operator.or_(view, operand)

    if operation in {"reflected_union", "union"}:
        assert len(result) == 9
        assert ("seed", "control") in result
        assert ("key-0", sentinel) in result
    elif operation == "subtraction":
        assert result == {("seed", "control")}
    else:
        assert result == set()
    del result
    gc.collect()
    assert sys.getrefcount(sentinel) == before
    assert list(mapping.items()) == [("seed", "control")]
