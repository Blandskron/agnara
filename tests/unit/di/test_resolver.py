import asyncio
from collections.abc import AsyncIterator, Iterator

from agnara.core.di import DIContainer, DIRegistry, Scope, compile_dag, provider


class Database:
    def __init__(self):
        self.connected = False

    def connect(self):
        self.connected = True

    def disconnect(self):
        self.connected = False


class AsyncCache:
    def __init__(self):
        self.connected = False

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False


@provider(scope=Scope.SINGLETON)
def provide_db() -> Iterator[Database]:
    db = Database()
    db.connect()
    yield db
    db.disconnect()


@provider(scope=Scope.INVOCATION)
async def provide_cache(db: Database) -> AsyncIterator[AsyncCache]:
    assert db.connected
    cache = AsyncCache()
    await cache.connect()
    yield cache
    await cache.disconnect()


def test_di_container_resolution_and_cleanup():
    async def run_test():
        registry = DIRegistry()
        registry.bind(Database, provide_db)
        registry.bind(AsyncCache, provide_cache)

        def my_handler(payload: str, cache: AsyncCache, db: Database) -> None:
            pass

        dag = compile_dag(registry, [my_handler])
        container = DIContainer(registry)

        db_instance = None
        cache_instance = None

        async with container.resolve_dependencies(my_handler, dag) as kwargs:
            cache = kwargs["cache"]
            db = kwargs["db"]
            db_instance = db
            cache_instance = cache

        assert cache_instance.connected is False
        assert db_instance.connected is True

        async with container.resolve_dependencies(my_handler, dag) as kwargs2:
            cache2 = kwargs2["cache"]
            db2 = kwargs2["db"]
            assert db2 is db_instance
            assert cache2 is not cache_instance

        await container.aclose()
        assert db_instance.connected is False

    asyncio.run(run_test())


def test_di_container_singleton_concurrency():
    """Verify E3.8 free-threading / asyncio concurrency safety assumptions."""

    class SlowSingleton:
        pass

    initialization_count = 0

    @provider(scope=Scope.SINGLETON)
    async def provide_slow() -> SlowSingleton:
        nonlocal initialization_count
        # Simulate an IO-bound initialization that forces context switch
        await asyncio.sleep(0.1)
        initialization_count += 1
        return SlowSingleton()

    async def run_test():
        registry = DIRegistry()
        registry.bind(SlowSingleton, provide_slow)

        def my_handler(slow: SlowSingleton) -> None:
            pass

        dag = compile_dag(registry, [my_handler])
        container = DIContainer(registry)

        async def worker():
            async with container.resolve_dependencies(my_handler, dag) as kwargs:
                return kwargs["slow"]

        # Run 100 concurrent resolutions
        results = await asyncio.gather(*(worker() for _ in range(100)))

        # Ensure that only ONE initialization happened despite 100 concurrent requests
        assert initialization_count == 1

        # Ensure all 100 workers got the exact same instance
        first_instance = results[0]
        for instance in results:
            assert instance is first_instance

        await container.aclose()

    asyncio.run(run_test())
