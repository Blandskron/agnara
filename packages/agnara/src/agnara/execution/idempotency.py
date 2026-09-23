"""Transport-neutral operational idempotency storage (ADR 0089).

This module defines a deliberately small storage port.  It does not select an
idempotency key from a transport, serialize a handler value, retry work, or
turn an operation into durable execution.  Callers pass an already validated
selector and an opaque serialized successful result; a store only arbitrates
the atomic state transitions required to reuse that result safely.
"""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import RLock
from typing import Protocol, runtime_checkable

from agnara._frozen import frozen_slots_dataclass
from agnara.capability.identity import CapabilityId
from agnara.errors import DefinitionError
from agnara.execution._execution_identity import ExecutionId

__all__: list[str] = []


_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._~-]*\Z")
_MAX_KEY_LENGTH = 128
_MAX_PRINCIPAL_LENGTH = 256
_MAX_FINGERPRINT_LENGTH = 64
_MAX_RESULT_LENGTH = 1_048_576


class IdempotencyStorageError(RuntimeError):
    """The configured idempotency store cannot safely serve an operation.

    Applications decide how a storage outage is projected.  This error is not
    a canonical capability failure, because the runtime is not the store's
    owner and must not silently turn storage loss into a retry.
    """


class IdempotencyConflictError(RuntimeError):
    """A selector cannot be used for the current logical invocation."""


class IdempotencyInProgressError(RuntimeError):
    """A matching selector is currently owned by another invocation."""


@runtime_checkable
class IdempotencyResultCodec(Protocol):
    """Encode and decode only successful values for an idempotency store.

    The application or an approved adapter owns this trusted boundary.  Core
    deliberately does not choose JSON, pickle, a schema library, or any
    result sensitivity policy.
    """

    def encode(self, value: object, /) -> bytes:
        """Return bounded opaque bytes for a successful value."""

    def decode(self, payload: bytes, /) -> object:
        """Return the successful value represented by stored bytes."""


@frozen_slots_dataclass
class IdempotencyInvocation:
    """Explicit runtime opt-in for one idempotent complete-result invocation.

    It is intentionally a context argument rather than invocation metadata:
    a transport cannot accidentally promote arbitrary caller metadata into a
    replay selector.  The runtime additionally checks the scope against its
    compiled capability and resolved principal before it calls the store.
    """

    scope: IdempotencyScope
    store: IdempotencyStore
    codec: IdempotencyResultCodec
    lease_ttl: float
    result_ttl: float

    def __post_init__(self) -> None:
        _validate_scope(self.scope)
        if not isinstance(self.store, IdempotencyStore):
            raise TypeError("store must satisfy IdempotencyStore")
        if not isinstance(self.codec, IdempotencyResultCodec):
            raise TypeError("codec must satisfy IdempotencyResultCodec")
        object.__setattr__(self, "lease_ttl", _validate_ttl(self.lease_ttl, name="lease_ttl"))
        object.__setattr__(
            self,
            "result_ttl",
            _validate_ttl(self.result_ttl, name="result_ttl"),
        )


@frozen_slots_dataclass
class IdempotencyScope:
    """The untrusted selector bound to one capability and principal.

    ``fingerprint`` is caller-produced canonical request material, normally a
    cryptographic digest.  The port deliberately does not prescribe payload
    serialization or a hash algorithm.  Keys and fingerprints are excluded
    from ``repr`` so a normal diagnostic cannot disclose them.
    """

    capability_id: CapabilityId
    principal_id: str = field(repr=False)
    key: str = field(repr=False)
    fingerprint: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.capability_id, CapabilityId):
            raise DefinitionError("capability_id must be a CapabilityId")
        if not isinstance(self.principal_id, str) or not self.principal_id:
            raise DefinitionError("principal_id must be a non-empty string")
        if len(self.principal_id) > _MAX_PRINCIPAL_LENGTH:
            raise DefinitionError(
                f"principal_id must not exceed {_MAX_PRINCIPAL_LENGTH} characters"
            )
        if not isinstance(self.key, str) or not _KEY.fullmatch(self.key):
            raise DefinitionError(
                "idempotency key must be a non-empty ASCII token containing only "
                "letters, digits, '.', '_', '~', or '-'"
            )
        if len(self.key) > _MAX_KEY_LENGTH:
            raise DefinitionError(f"idempotency key must not exceed {_MAX_KEY_LENGTH} characters")
        if not isinstance(self.fingerprint, bytes) or not self.fingerprint:
            raise DefinitionError("fingerprint must be non-empty bytes")
        if len(self.fingerprint) > _MAX_FINGERPRINT_LENGTH:
            raise DefinitionError(f"fingerprint must not exceed {_MAX_FINGERPRINT_LENGTH} bytes")


@frozen_slots_dataclass
class IdempotencyReservation:
    """The private capability to complete or abandon one accepted claim."""

    scope: IdempotencyScope
    execution_id: str
    token: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.scope, IdempotencyScope):
            raise TypeError("scope must be an IdempotencyScope")
        ExecutionId(self.execution_id)
        ExecutionId(self.token)


@frozen_slots_dataclass
class IdempotencyClaimed:
    """A caller atomically acquired the right to execute a capability once."""

    reservation: IdempotencyReservation


@frozen_slots_dataclass
class IdempotencyInProgress:
    """A matching caller must wait for the existing reservation to settle."""

    execution_id: str

    def __post_init__(self) -> None:
        ExecutionId(self.execution_id)


@frozen_slots_dataclass
class IdempotencyCompleted:
    """A matching caller can reuse an opaque, previously stored success."""

    execution_id: str
    result: bytes = field(repr=False)

    def __post_init__(self) -> None:
        ExecutionId(self.execution_id)
        _validate_result(self.result)


@frozen_slots_dataclass
class IdempotencyConflict:
    """The selector was reused with a different request fingerprint.

    This deliberately contains no prior execution, fingerprint, or result:
    revealing any of them would cross a caller-controlled selector boundary.
    """


@runtime_checkable
class IdempotencyStore(Protocol):
    """A pluggable atomic store for idempotency reservations and successes.

    Every method is async so a Redis or PostgreSQL implementation can provide
    one atomic operation without a thread-pool wrapper.  The protocol itself
    does not name transactions, commands, drivers, or serialization formats.
    ``complete`` receives only an already serialized successful result; the
    invocation boundary owns redaction, serialization, and any future result
    projection.  Failures and cancellations call ``abandon`` and are never
    cached by this contract.
    """

    async def claim(
        self, scope: IdempotencyScope, *, lease_ttl: float
    ) -> IdempotencyClaimed | IdempotencyInProgress | IdempotencyCompleted | IdempotencyConflict:
        """Atomically reserve a selector or return its existing state."""

    async def lookup(
        self, scope: IdempotencyScope
    ) -> IdempotencyInProgress | IdempotencyCompleted | IdempotencyConflict | None:
        """Read the current state without obtaining a reservation."""

    async def complete(
        self, reservation: IdempotencyReservation, result: bytes, *, result_ttl: float
    ) -> bool:
        """Atomically publish a success if ``reservation`` is still current."""

    async def abandon(self, reservation: IdempotencyReservation) -> bool:
        """Atomically release a current failed or cancelled reservation."""


@dataclass(slots=True)
class _Record:
    fingerprint: bytes
    execution_id: str
    token: str | None
    expires_at: float
    result: bytes | None = None


class InMemoryIdempotencyStore:
    """A bounded, process-local reference implementation of :class:`IdempotencyStore`.

    It is suitable for deterministic tests and a single process only.  Its
    monotonic clock, lock, and records are neither durable nor shared across
    processes, machines, or restarts.  Production deployments need an
    application-owned implementation of :class:`IdempotencyStore`.
    """

    def __init__(
        self,
        *,
        max_entries: int = 1_024,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 1:
            raise ValueError("max_entries must be a positive integer")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock
        self._max_entries = max_entries
        self._lock = RLock()
        self._records: dict[tuple[CapabilityId, str, str], _Record] = {}

    async def claim(
        self, scope: IdempotencyScope, *, lease_ttl: float
    ) -> IdempotencyClaimed | IdempotencyInProgress | IdempotencyCompleted | IdempotencyConflict:
        _validate_scope(scope)
        ttl = _validate_ttl(lease_ttl, name="lease_ttl")
        now = self._now()
        selector = _selector(scope)
        with self._lock:
            record = self._live(selector, now)
            if record is None:
                if len(self._records) >= self._max_entries:
                    # Only sweep when space is actually needed. Sweeping on every
                    # operation made each call linear in the number of stored
                    # records, so a busy process paid quadratic cost overall.
                    self._discard_expired(now)
                if len(self._records) >= self._max_entries:
                    raise IdempotencyStorageError("idempotency store capacity exhausted")
                reservation = IdempotencyReservation(
                    scope=scope,
                    execution_id=ExecutionId.generate().value,
                    token=ExecutionId.generate().value,
                )
                self._records[selector] = _Record(
                    fingerprint=scope.fingerprint,
                    execution_id=reservation.execution_id,
                    token=reservation.token,
                    expires_at=now + ttl,
                )
                return IdempotencyClaimed(reservation)
            return _state(scope, record)

    async def lookup(
        self, scope: IdempotencyScope
    ) -> IdempotencyInProgress | IdempotencyCompleted | IdempotencyConflict | None:
        _validate_scope(scope)
        now = self._now()
        with self._lock:
            record = self._live(_selector(scope), now)
            return None if record is None else _state(scope, record)

    async def complete(
        self, reservation: IdempotencyReservation, result: bytes, *, result_ttl: float
    ) -> bool:
        _validate_reservation(reservation)
        _validate_result(result)
        ttl = _validate_ttl(result_ttl, name="result_ttl")
        now = self._now()
        selector = _selector(reservation.scope)
        with self._lock:
            record = self._live(selector, now)
            if record is None or record.token != reservation.token:
                return False
            record.token = None
            record.result = result
            record.expires_at = now + ttl
            return True

    async def abandon(self, reservation: IdempotencyReservation) -> bool:
        _validate_reservation(reservation)
        now = self._now()
        selector = _selector(reservation.scope)
        with self._lock:
            record = self._live(selector, now)
            if record is None or record.token != reservation.token:
                return False
            del self._records[selector]
            return True

    def _now(self) -> float:
        value = self._clock()
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not math.isfinite(value)
        ):
            raise IdempotencyStorageError("clock must return a finite number")
        return float(value)

    def _live(self, selector: tuple[CapabilityId, str, str], now: float) -> _Record | None:
        """Return the record for ``selector``, dropping it if it has expired.

        Expiry is resolved for the one record being touched rather than by
        sweeping the whole store, so an operation costs the same whether the
        store holds ten records or ten thousand. The boundary stays ``<= now``,
        so a record expires exactly when its deadline is reached.
        """
        record = self._records.get(selector)
        if record is None:
            return None
        if record.expires_at <= now:
            del self._records[selector]
            return None
        return record

    def _discard_expired(self, now: float) -> None:
        for selector, record in tuple(self._records.items()):
            if record.expires_at <= now:
                del self._records[selector]


def _selector(scope: IdempotencyScope) -> tuple[CapabilityId, str, str]:
    return scope.capability_id, scope.principal_id, scope.key


def _state(
    scope: IdempotencyScope, record: _Record
) -> IdempotencyInProgress | IdempotencyCompleted | IdempotencyConflict:
    if scope.fingerprint != record.fingerprint:
        return IdempotencyConflict()
    if record.token is not None:
        return IdempotencyInProgress(record.execution_id)
    if record.result is None:
        raise IdempotencyStorageError("idempotency store contains incompatible state")
    return IdempotencyCompleted(record.execution_id, record.result)


def _validate_scope(scope: IdempotencyScope) -> None:
    if not isinstance(scope, IdempotencyScope):
        raise TypeError("scope must be an IdempotencyScope")


def _validate_reservation(reservation: IdempotencyReservation) -> None:
    if not isinstance(reservation, IdempotencyReservation):
        raise TypeError("reservation must be an IdempotencyReservation")


def _validate_ttl(value: float, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite positive number")
    if value <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return float(value)


def _validate_result(result: bytes) -> None:
    if not isinstance(result, bytes):
        raise TypeError("result must be bytes")
    if len(result) > _MAX_RESULT_LENGTH:
        raise ValueError(f"result must not exceed {_MAX_RESULT_LENGTH} bytes")
