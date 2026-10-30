# Isolated A2A SDK feasibility probe

This is A2A-01 evidence for [RFC 0010](../../docs/rfc/0010-a2a-initial-projection.md),
not an Agnara adapter or application example. The
[report](../../docs/research/a2a-initial-feasibility.md) owns conclusions and limits.
No `agnara_a2a` API is added. The workspace environment does not need the SDK.

Run from the repository root on conventional CPython 3.14. The retained run
used Windows 11 and Python 3.14.4 with the GIL enabled; no other OS or
free-threaded build was tested. The lock is this Windows/Python resolution,
not a universal-platform lock.

```powershell
uv venv experiments/a2a/.venv --python 3.14.4
uv pip sync --require-hashes --python experiments/a2a/.venv/Scripts/python.exe experiments/a2a/requirements.lock
experiments/a2a/.venv/Scripts/python.exe experiments/a2a/probe.py
```

The environment is ignored by the repository's existing `.venv/` rule. Never
install these requirements into the workspace environment or copy their pins
into a distributable package based on this experiment. The initial lock was
produced with the command recorded at its top; regenerate it only as a new
reviewed evidence checkpoint.

The script dynamically imports the isolated SDK modules, then executes actual
SDK calls. This keeps workspace typing/import checks independent of a new SDK
dependency. It uses the official JSON-RPC client transport, official Starlette
route factories and generated protobuf models. A minimal stateless handler
and the official `DefaultRequestHandler` are probed separately. The echo
executor is fixture logic; it neither invokes nor reimplements Agnara.

HTTPX's ASGI transport dispatches in process; `fixture.invalid` is never
contacted over the network. Installation requires package-index access.
The script explicitly enters Starlette lifespan, closes the shared client
before the handler, bounds work with timeouts and asserts no remaining tasks.
Expected SDK refusal diagnostics appear on stderr. Stdout is a JSON evidence
document; assertion failures or unexpected exceptions exit nonzero.

[observed-windows.json](observed-windows.json) retains one successful run:
interpreter/OS/GIL state, all 30 installed distribution versions, source/lock
hashes, inspected SDK source hashes and observed results. The hashes identify
the tested source bytes without claiming that an uncommitted run was already
a Git commit. Four inspected installed SDK files were also hash-compared with
the immutable upstream commit cited in the report.

The probes intentionally demonstrate permissive parsing and numeric/version
limitations rather than correcting them. They are regression evidence for a
research checkpoint, not a server conformance suite, authenticated deployment
or proposal to change Agnara's domain semantics.

## A2A-03 adapter fixture

[fixture.py](fixture.py) is an internal, experiment-only implementation of the
[ADR 0098](../../docs/adr/0098-a2a-complete-result-projection.md) profile. It
consists of an admission gate in front of the SDK, a context builder that
passes only the resolved principal and the `A2A-Version` header, and a no-task
`RequestHandler`. That handler invokes compiled Agnara plans through public
`agnara.execution.invoke_result`. The kernel decides every capability outcome;
the fixture validates the envelope, converts numbers and projects outcomes.
[fixture_probe.py](fixture_probe.py) drives it through the official JSON-RPC
client and raw ASGI requests and asserts each row against the amended
ADR 0098. Where an observation differs from the record, it adds a
`deviations` entry instead of failing; the retained run has none.

The fixture also needs the workspace `agnara` kernel in the same isolated
environment. Install it without dependencies (the kernel has none) and run the
probe as a module from the repository root:

```powershell
uv pip install --no-deps --python experiments/a2a/.venv/Scripts/python.exe ./packages/agnara
experiments/a2a/.venv/Scripts/python.exe -m experiments.a2a.fixture_probe
```

This does not modify `requirements.lock`. The installed kernel is the current
checkout, not a published wheel. A later rerun of `probe.py` in the same
environment therefore lists 31 distributions rather than the 30 retained for
A2A-01. [observed-fixture-windows.json](observed-fixture-windows.json)
retains one successful run on the same Windows/Python 3.14.4 environment as
A2A-01, with source hashes. Expected SDK refusal diagnostics appear on stderr.
The fixture is not an `agnara-a2a` API, example or support claim.

## Proposed host disconnect policy

[disconnect_policy.py](disconnect_policy.py) is a separate, stdlib-only
prototype for [Proposed ADR 0100](../../docs/adr/0100-opt-in-host-disconnect-cancellation.md).
It does not extend the earlier SDK experiment or change `requirements.lock`.
Run its synthetic and real-loopback tests using the current workspace's
pinned A2A/Uvicorn development environment:

```bash
uv sync --locked
uv run pytest tests/a2a/test_disconnect_policy_experiment.py tests/a2a/test_a2a_network.py
```

The experiment lazily owns the receive stream, passes body events through a
bounded FIFO and joins its application/pump tasks. It cancels pending work on
a peer disconnect without waiting for the kernel deadline, preserves outer
cancellation/errors, and leaves completed-response cleanup alone. No shipped
package or runnable application imports it. Keep the unwrapped network tests:
they prove the public adapter's existing deadline-owned behavior still holds.
The ADR proposes a host policy and a future scope; it does not ship or approve
a production wrapper, new API, support claim or maturity promotion.
