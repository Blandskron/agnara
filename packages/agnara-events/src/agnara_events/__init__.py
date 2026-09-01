"""Event exposure abstractions for Agnara capabilities.

Owns the event capability abstractions and AsyncAPI projection. Broker
specifics (Kafka, NATS, RabbitMQ) belong in separate plugin packages and
must not be hardcoded here.

Depends on ``agnara-core``. Must not import a sibling adapter.
See ``ARCHITECTURE.md`` sections 3 and 4, and Post-v0.1 in ``BACKLOG.md``.
"""
