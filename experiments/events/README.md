# EVT-01 inventory snapshot feasibility

[Issue #783](https://github.com/Blandskron/agnara/issues/783) tests the inbound
case from [RFC 0011](../../docs/rfc/0011-event-initial-projection.md) with
RabbitMQ 4.2.5, aio-pika 9.6.1 and a transactional SQLite read model. It uses
the public Agnara schema and invocation contracts and the repository's
experimental Pydantic schema adapter.

Run from the repository root with PowerShell 7, a running Linux Docker engine
and conventional CPython 3.14.4. The retained run used Windows 11 x64, Docker
29.9.3 and SQLite 3.50.4. The dependency lock belongs to this experiment.

```powershell
uv venv experiments/events/.venv --python 3.14.4
uv pip sync --require-hashes --python experiments/events/.venv/Scripts/python.exe experiments/events/requirements.lock
uv pip install --no-deps --python experiments/events/.venv/Scripts/python.exe ./packages/agnara
& ./experiments/events/run.ps1
```

The runner starts a disposable broker from the pinned image digest and
binds AMQP to a random loopback port. It creates separate publisher
credentials, applies the quorum dead-letter policy and removes the named
container and its anonymous volume on exit. The probe prints JSON evidence
after its assertions pass. The three forced failures emit expected diagnostics
to stderr.

| Observation | Result |
| --- | --- |
| Authority and input | RabbitMQ denied a publisher without exchange write permission. A producer-asserted scope could not authorize the invocation. A wrong event type, missing scope and invalid inputs acquired no store connection. |
| Commit and acknowledgement | While a write was held open, a separate connection saw no commit and the delivery remained unsettled. Closing the delivery channel after commit and before acknowledgement caused redelivery with count 1. Replaying that revision left the write count unchanged. |
| Revision and conflict | SQLite received `9007199254740993` exactly. A stale snapshot succeeded without a write, a conflicting equal revision went to the dead-letter queue, and a newer revision with a reused envelope ID updated the read model. The read model also stored `9223372036854775808` units as decimal text to preserve quantities beyond SQLite's signed integer range. |
| Retry and shutdown | The forced transient failure produced counts 0, 1 and 2 before dead-lettering for `delivery_limit`. Cancelling a blocked invocation rolled back its write and closed its connection. The host stopped consuming before releasing the delivery, then observed one redelivery and committed it once. The probe exited with no pending tasks. |
| Schema | The compiled Pydantic schemas supplied the string and integer bounds through named type aliases. The built-in fixed tuple schema translated from `prefixItems` and `items: false` to Draft 07 array-form `items` and `additionalItems: false`. Draft 07 accepted `2.0` as an integer while strict runtime validation refused it. |

The fixture opens asynchronous AMQP connections with `connect`, so reconnect
is explicit. The client defaults to publisher confirms and manual consumer
acknowledgement. The probe sets prefetch to 1 and uses one invocation at a time.
It creates no worker threads. Consumer ACK and reject methods send frames
without waiting for a broker response. The replay observations come from the
broker and the committed write counts come from SQLite.
[aio-pika API](https://docs.aio-pika.com/apidoc.html)

The single-node run covers delivery-channel loss and coroutine cancellation.
Cluster failover, broker restart and automatic reconnect remain unmeasured.
The inventory conflict is a declared business result projected by the fixture.
The probe translates one fixed tuple schema and does not generate an AsyncAPI
document. EVT-02 needs decisions on strict numeric schema semantics, supported
translations, error projection and which settlement guarantees the public
contract can describe. [RabbitMQ quorum queues](https://www.rabbitmq.com/docs/4.2/quorum-queues)
