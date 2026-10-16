"""Negative proofs for the installed-guide behavior/effects/cleanup gate."""

from __future__ import annotations

import pytest

from tests.release.test_integrated_dogfooding import (
    assert_fastapi_guide_output,
    assert_host_guide_output,
    assert_sqlite_guide_output,
)

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


FASTAPI_VALID = """authorized, scoped             -> 200 {"order":"A-1","status":"shipped"}
authenticated, missing scope   -> 403 {"error":"forbidden"}
unknown credential             -> 401 {"detail":"unauthenticated"}
no credential                  -> 401 {"detail":"unauthenticated"}
plain FastAPI route            -> 200 {"status":"ok"}
correlation accepted           -> 'req-7f3a9c'
correlation dropped (long)     -> None
correlation dropped (token)    -> None

The capability never saw the request object, an unmapped
credential was refused rather than executed anonymously, and
unbounded request data never reached a tracking_id.
"""

SQLITE_VALID = """success: committed
denied: forbidden
invalid: invalid_input
failed: internal_failure
cancelled: CancelledError
persisted: ('committed',)
events: ['session.open', 'port.open', 'write:committed', 'port.close', 'host.commit', 'host.rollback', 'host.rollback', 'port.open', 'write:rolled-back', 'port.close', 'host.rollback', 'port.open', 'write:cancelled', 'port.close', 'host.rollback', 'runtime.close', 'session.close', 'engine.dispose']
"""  # noqa: E501 -- exact stdout fixture, including the complete ordered event trace.


def test_fastapi_output_accepts_json_whitespace_and_explanatory_prose() -> None:
    assert_fastapi_guide_output(FASTAPI_VALID)
    assert_fastapi_guide_output(FASTAPI_VALID.replace('{"status":"ok"}', '{"status": "ok"}'))


@pytest.mark.parametrize(
    "invalid",
    [
        FASTAPI_VALID.replace(
            'no credential                  -> 401 {"detail":"unauthenticated"}\n', ""
        ),
        FASTAPI_VALID + 'no credential -> 401 {"detail":"unauthenticated"}\n',
        FASTAPI_VALID.replace('403 {"error":"forbidden"}', '200 {"error":"forbidden"}'),
        FASTAPI_VALID.replace('"order":"A-1"', '"order":"A-2"'),
        FASTAPI_VALID.replace('"status":"ok"', '"status":"ok","private":"leak"'),
        FASTAPI_VALID.replace("-> 'req-7f3a9c'", "-> None"),
        FASTAPI_VALID.replace("(long)     -> None", "(long)     -> 'unbounded'"),
        FASTAPI_VALID.replace("(token)    -> None", "(token)    -> 'injected'"),
        FASTAPI_VALID + "unexpected -> None\n",
    ],
)
def test_fastapi_incomplete_or_incorrect_output_is_rejected(invalid: str) -> None:
    with pytest.raises(AssertionError):
        assert_fastapi_guide_output(invalid)


def test_sqlite_output_accepts_literal_whitespace() -> None:
    assert_sqlite_guide_output(SQLITE_VALID)
    assert_sqlite_guide_output(SQLITE_VALID.replace("('committed',)", "( 'committed', )"))


@pytest.mark.parametrize(
    "invalid",
    [
        SQLITE_VALID.replace("denied: forbidden\n", ""),
        SQLITE_VALID + "success: committed\n",
        SQLITE_VALID.replace("denied: forbidden", "denied: committed"),
        SQLITE_VALID.replace("invalid: invalid_input", "invalid: committed"),
        SQLITE_VALID.replace("failed: internal_failure", "failed: committed"),
        SQLITE_VALID.replace("cancelled: CancelledError", "cancelled: committed"),
        SQLITE_VALID.replace("('committed',)", "('committed', 'rolled-back')"),
        SQLITE_VALID.replace("('committed',)", "('committed', 'cancelled')"),
        SQLITE_VALID.replace("'host.rollback', 'host.rollback'", "'port.open', 'host.rollback'"),
        SQLITE_VALID.replace("'host.rollback'", "'host.commit'"),
        SQLITE_VALID.replace("'port.close', ", ""),
        SQLITE_VALID.replace(
            "'runtime.close', 'session.close'", "'session.close', 'runtime.close'"
        ),
        SQLITE_VALID.replace(
            "'session.close', 'engine.dispose'", "'engine.dispose', 'session.close'"
        ),
        SQLITE_VALID + "unexpected: true\n",
    ],
)
def test_sqlite_incomplete_or_incorrect_output_is_rejected(invalid: str) -> None:
    with pytest.raises(AssertionError):
        assert_sqlite_guide_output(invalid)
