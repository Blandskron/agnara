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


def test_di_container_resolves_bound_parameters_once_per_callable(monkeypatch):
    """Resolving type hints costs microseconds per callable per call; the
    container resolves each callable's bindings once and reuses them, and the
    reuse must not change which parameters receive which dependency."""
    import typing

    class Left:
        pass

    class Right:
        pass

    @provider()
    def provide_left() -> Left:
        return Left()

    @provider()
    def provide_right() -> Right:
        return Right()

    async def run_test():
        registry = DIRegistry()
        registry.bind(Left, provide_left)
        registry.bind(Right, provide_right)

        def my_handler(payload: str, right: Right, left: Left) -> None:
            pass

        dag = compile_dag(registry, [my_handler])
        container = DIContainer(registry)

        calls = 0
        original = typing.get_type_hints

        def counting(obj, *args, **kwargs):
            nonlocal calls
            calls += 1
            return original(obj, *args, **kwargs)

        import agnara.core.di.compiler as compiler

        monkeypatch.setattr(compiler, "get_type_hints", counting)
        for _ in range(5):
            async with container.resolve_dependencies(my_handler, dag) as kwargs:
                assert set(kwargs) == {"right", "left"}
                assert type(kwargs["right"]) is Right
                assert type(kwargs["left"]) is Left
        # One resolution for the handler and one per provider, not one per call.
        assert calls == 3
        await container.aclose()

    asyncio.run(run_test())


def test_di_container_invocation_cache_is_shared_within_one_resolution():
    """Two parameters bound to the same invocation-scoped type receive one
    instance, and a provider depending on that type receives the same one."""

    class Unit:
        pass

    class Wrapper:
        def __init__(self, unit: Unit):
            self.unit = unit

    built = 0

    @provider()
    def provide_unit() -> Unit:
        nonlocal built
        built += 1
        return Unit()

    @provider()
    def provide_wrapper(unit: Unit) -> Wrapper:
        return Wrapper(unit)

    async def run_test():
        registry = DIRegistry()
        registry.bind(Unit, provide_unit)
        registry.bind(Wrapper, provide_wrapper)

        def my_handler(unit: Unit, wrapper: Wrapper) -> None:
            pass

        dag = compile_dag(registry, [my_handler])
        container = DIContainer(registry)
        async with container.resolve_dependencies(my_handler, dag) as kwargs:
            assert kwargs["wrapper"].unit is kwargs["unit"]
        assert built == 1
        async with container.resolve_dependencies(my_handler, dag) as kwargs:
            pass
        assert built == 2

    asyncio.run(run_test())
