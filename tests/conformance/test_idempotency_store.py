import asyncio

from agnara.execution.idempotency import InMemoryIdempotencyStore

from .idempotency_store import assert_idempotency_store_conforms


def test_in_memory_store_satisfies_the_reusable_conformance_contract() -> None:
    asyncio.run(
        assert_idempotency_store_conforms(
            lambda clock, max_entries: InMemoryIdempotencyStore(
                max_entries=max_entries, clock=clock
            )
        )
    )
