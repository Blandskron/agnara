# WS-01 — WebSocket streaming feasibility boundary

[Issue #819](https://github.com/Blandskron/agnara/issues/819) tests the inbound
WebSocket streaming questions in [RFC 0013](../../docs/rfc/0013-websocket-streaming-projection.md)
against Agnara's public streaming (`open_stream`, `StreamTerminal`,
`StreamInterrupted`), schema (`materialize_json`, `serialize_json`), policy and DI
contracts.

This experiment uses only Python's standard library and canonical public
`agnara` exports. It adds no runtime package API and claims no WebSocket support
beyond the isolated harness below.

## Reproduce

Run from the repository root with Python 3.14:

```sh
uv sync --locked
uv run python scripts/check_public_imports.py experiments/websocket
uv run python -m experiments.websocket.probe
```

[Retained output](observed-windows.json) was recorded on CPython 3.14.4 with the
local ASGI harness and stdlib `127.0.0.1:0` RFC 6455 TCP loopback fixtures.

## Feasibility observations

| Observation | Result | RFC 0013 question |
| --- | --- | --- |
| Origin rejection before accept | Missing or untrusted `Origin` closed pre-accept with RFC 6455 code `1008` in-process and HTTP `403` over TCP loopback, opening `0` DI providers. | Q2 |
| Pre-DI policy refusal | Option A (`handshake`) closed pre-accept with `1008`; Option B (`initial_frame`) emitted `failed` (`forbidden`) + `1008`, opening `0` DI providers. | Q2, Q3 |
| Handshake vs. initial-frame inputs | Option A bound query parameters and pulled unit 1 before `websocket.accept`; Option B enforced `max_frame_bytes` (`1009`), valid JSON object syntax and strict schema validation (`invalid_input`, `1008`). | Q3, Q4 |
| Pre- vs. post-output failure and oversize units | Unexpected exception before unit 1 emitted `failed` (`units: 0`); after unit 1 emitted `interrupted` (`units: 1`), both with redacted `internal_failure` (`"capability invocation failed"`) and code `1011` and zero diagnostic leakage. An oversized outbound unit failed without truncation. | Q4 |
| Pull backpressure and disconnect cancellation | Holding `websocket.send` prevented producer entry into unit 2; sending `websocket.disconnect` (or dropping TCP abruptly on loopback) cancelled the suspended producer task and tore down `Scope.INVOCATION` resources on the owning loop. | Q5, Q6, Q9 |
| Monotonic deadline and concurrent isolation | A short `attempt_timeout` emitted `timed_out` + `1011` cleanly after unit 1; concurrent streams isolated distinct `Scope.INVOCATION` resources while keeping shared `Scope.SINGLETON` open until `container.aclose()`, exiting with `surviving_tasks: 0`. | Q6, Q9 |

## Explicit limits

- Covers unidirectional server streams (`open_stream`) only; bidirectional frames,
  subprotocols, ping/pong keepalive policies and proxy timeouts remain host/future-ADR
  questions.
- The RFC 6455 loopback server and client in `experiments/websocket/loopback.py`
  are stdlib test fixtures for single-machine loopback evidence, not an ASGI
  server or WebSocket client recommendation.
