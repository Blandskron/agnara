"""WS-01 — executable evidence for RFC 0013 WebSocket streaming projection."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from experiments.websocket.probe import run_probe

_ROOT = Path(__file__).resolve().parents[2]
_CHECKER = _ROOT / "scripts" / "check_public_imports.py"
_EXPERIMENT_DIR = _ROOT / "experiments" / "websocket"


def test_websocket_experiment_uses_only_public_agnara_imports() -> None:
    result = subprocess.run(
        [sys.executable, str(_CHECKER), str(_EXPERIMENT_DIR)],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_websocket_probe_scenarios_pass_with_zero_leaked_tasks() -> None:
    observed = asyncio.run(run_probe())
    assert observed["experiment"] == "WS-01"
    assert observed["surviving_tasks"] == 0
    assert observed["scenarios"]["origin_rejected_before_accept"]["di_opens"] == 0
    assert observed["scenarios"]["policy_denied_before_di"]["di_opens"] == 0
    assert observed["scenarios"]["option_a_completed_and_empty"]["di_closed"] == 2
    assert observed["scenarios"]["option_b_input_contracts"]["oversized_initial_close"] == 1009
    assert observed["scenarios"]["redaction_and_oversize"]["oversize_unit_refused"] is True
    assert (
        observed["scenarios"]["backpressure_and_disconnect"]["disconnect_cancelled_producer"]
        is True
    )
    assert observed["scenarios"]["deadline_and_concurrency"]["singleton_lifetime_preserved"] is True
    assert observed["scenarios"]["tcp_loopback_rfc6455"]["abrupt_tcp_drop_cleaned"] is True
