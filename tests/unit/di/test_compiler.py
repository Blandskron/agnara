import pytest

from agnara.core.di import (
    DependencyCycleError,
    DependencyResolutionError,
    DIRegistry,
    compile_dag,
    provider,
)


class Database:
    pass


class Repository:
    pass


class Service:
    pass


@provider()
def provide_db() -> Database:
    return Database()


@provider()
def provide_repo(db: Database) -> Repository:
    return Repository()


@provider()
def provide_service(repo: Repository) -> Service:
    return Service()


def test_compile_dag_success():
    registry = DIRegistry()
    registry.bind(Database, provide_db)
    registry.bind(Repository, provide_repo)
    registry.bind(Service, provide_service)

    def my_capability(payload: dict, svc: Service, db: Database) -> None:
        pass

    deps = compile_dag(registry, [my_capability])

    assert my_capability in deps
    assert Service in deps[my_capability]
    assert Database in deps[my_capability]
    # 'payload' is ignored because it's not in the registry


def test_compile_dag_detects_cycle():
    class A:
        pass

    class B:
        pass

    @provider()
    def provide_a(b: B) -> A:
        return A()

    @provider()
    def provide_b(a: A) -> B:
        return B()

    registry = DIRegistry()
    registry.bind(A, provide_a)
    registry.bind(B, provide_b)

    def my_cap(a: A) -> None:
        pass

    with pytest.raises(DependencyCycleError, match="Dependency cycle detected"):
        compile_dag(registry, [my_cap])


def test_compile_dag_provider_unbound_dependency():
    class Missing:
        pass

    @provider()
    def bad_provider(m: Missing) -> Database:
        return Database()

    registry = DIRegistry()
    registry.bind(Database, bad_provider)

    def my_cap(db: Database) -> None:
        pass

    with pytest.raises(
        DependencyResolutionError, match="Providers can only depend on other registered providers"
    ):
        compile_dag(registry, [my_cap])


def test_registry_bind_invalid():
    registry = DIRegistry()

    def plain_func() -> Database:
        return Database()

    with pytest.raises(TypeError, match="must be a ProviderDefinition"):
        registry.bind(Database, plain_func)
