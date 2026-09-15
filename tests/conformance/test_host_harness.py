from __future__ import annotations

import pytest

from tests.conformance.harness import (
    BrokenHostFixture,
    DirectAgnaraHost,
    HostContractError,
    HostHarness,
    SideBySideHost,
)


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        (DirectAgnaraHost("demo"), "sync:demo:42"),
    ],
)
def test_harness_accepts_a_direct_agnara_host(host: DirectAgnaraHost, expected: str) -> None:
    harness = HostHarness()

    assert (
        harness.run_case(
            host,
            "sync",
            lambda fixture: fixture.call_sync(42),
            lambda value: value == expected,
        )
        == expected
    )
    assert host.events == ["start", "sync", "stop"]


def test_harness_catches_a_broken_host_fixture() -> None:
    host = BrokenHostFixture("broken")
    harness = HostHarness()

    with pytest.raises(HostContractError, match=r"startup|shutdown|cleanup"):
        harness.run_case(
            host,
            "sync",
            lambda fixture: fixture.call_sync("bad"),
            lambda value: value == "ok",
        )


def test_harness_supports_side_by_side_process_lifecycles() -> None:
    native = SideBySideHost("native")
    agnara = SideBySideHost("agnara")

    harness = HostHarness()
    result = harness.run_side_by_side(
        native,
        agnara,
        lambda fixture: fixture.call_sync("ping"),
        lambda value: value.startswith("sync:"),
    )

    assert result == {
        "native": "sync:native:ping",
        "agnara": "sync:agnara:ping",
    }
    assert native.events == ["start", "sync", "stop"]
    assert agnara.events == ["start", "sync", "stop"]
