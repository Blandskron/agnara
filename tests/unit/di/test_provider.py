from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator

import pytest

from agnara.core.di.provider import ProviderType, Scope, provider


def test_sync_function_provider():
    @provider(scope=Scope.SINGLETON)
    def provide_int() -> int:
        return 42

    assert provide_int.scope == Scope.SINGLETON
    assert provide_int.provider_type == ProviderType.SYNC_FUNCTION
    assert provide_int.return_type is int


def test_async_function_provider():
    @provider()
    async def provide_str() -> str:
        return "hello"

    assert provide_str.scope == Scope.INVOCATION
    assert provide_str.provider_type == ProviderType.ASYNC_FUNCTION
    assert provide_str.return_type is str


def test_sync_generator_provider():
    @provider()
    def provide_float() -> Iterator[float]:
        yield 3.14

    assert provide_float.provider_type == ProviderType.SYNC_GENERATOR
    assert provide_float.return_type is float


def test_async_generator_provider():
    @provider()
    async def provide_bytes() -> AsyncIterator[bytes]:
        yield b"data"

    assert provide_bytes.provider_type == ProviderType.ASYNC_GENERATOR
    assert provide_bytes.return_type is bytes


def test_generator_class_provider():
    @provider()
    def provide_bool() -> Generator[bool]:
        yield True

    assert provide_bool.provider_type == ProviderType.SYNC_GENERATOR
    assert provide_bool.return_type is bool


def test_async_generator_class_provider():
    @provider()
    async def provide_list() -> AsyncGenerator[list]:
        yield []

    assert provide_list.provider_type == ProviderType.ASYNC_GENERATOR
    assert provide_list.return_type is list


def test_provider_missing_return_type():
    with pytest.raises(TypeError, match="must declare a return type hint"):

        @provider()
        def bad_provider():
            return 1
