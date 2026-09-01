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
    # Cache relies on DB to test cross-provider resolution
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

        # First invocation
        async with container.resolve_dependencies(my_handler, dag) as kwargs:
            assert "cache" in kwargs
            assert "db" in kwargs
            assert "payload" not in kwargs

            cache = kwargs["cache"]
            db = kwargs["db"]

            assert cache.connected
            assert db.connected

            db_instance = db
            cache_instance = cache

        # After invocation, INVOCATION cache should be torn down, SINGLETON should remain
        assert cache_instance.connected is False
        assert db_instance.connected is True

        # Second invocation to check cache reuse
        async with container.resolve_dependencies(my_handler, dag) as kwargs2:
            cache2 = kwargs2["cache"]
            db2 = kwargs2["db"]

            # Singleton reused
            assert db2 is db_instance
            # Invocation created new
            assert cache2 is not cache_instance

        # Close container
        await container.aclose()
        assert db_instance.connected is False

    asyncio.run(run_test())
