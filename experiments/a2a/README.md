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
