"""Negative proofs for the installed-guide behavior/effects/cleanup gate."""

from __future__ import annotations

import pytest

from tests.release.test_integrated_dogfooding import assert_host_guide_output

VALID = """success: 200 {"order_id":7}
policy denial: 403 {"error":"forbidden"}
unknown credential: 401 {"error":"unauthenticated"}
missing credential: 401 {"error":"unauthenticated"}
malformed JSON: 400 {"error":"malformed_json"}
invalid input: 422 {"error":"invalid_input"}
native health: 200 {"status":"ok"}
recorded orders: [7]
cleanup: ['audit.close', 'runtime.close']
"""


def test_valid_output_including_json_whitespace_is_accepted() -> None:
    assert_host_guide_output(VALID)
    assert_host_guide_output(VALID.replace('{"order_id":7}', '{"order_id": 7}'))


@pytest.mark.parametrize(
    "invalid",
    [
        VALID.replace('policy denial: 403 {"error":"forbidden"}\n', ""),
        VALID + 'success: 200 {"order_id":7}\n',
        VALID.replace("policy denial: 403", "policy denial: 200"),
        VALID.replace('{"order_id":7}', '{"order_id":8}'),
        VALID.replace('403 {"error":"forbidden"}', '403 {"error":"forbidden","private":"leak"}'),
        VALID.replace("recorded orders: [7]", "recorded orders: [7, 8]"),
        VALID.replace("['audit.close', 'runtime.close']", "['runtime.close', 'audit.close']"),
        VALID.replace("['audit.close', 'runtime.close']", "['runtime.close']"),
        VALID + "unexpected: true\n",
    ],
)
def test_incomplete_or_incorrect_behavior_is_rejected(invalid: str) -> None:
    with pytest.raises(AssertionError):
        assert_host_guide_output(invalid)
