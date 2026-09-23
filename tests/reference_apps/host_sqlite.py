"""Agnara-hosted consumer using an application-owned SQLAlchemy port."""

from __future__ import annotations

import asyncio

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from agnara import Agnara, App, CapabilityId
from agnara.di import DIContainer, DIRegistry, provider
from agnara.execution import ExecutionContext, ExecutionPlan, Invocation, Success, invoke_result


class Ledger:
    """Application port: the handler never receives a SQLAlchemy session."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, value: str) -> int:
        self._session.execute(text("insert into entries (value) values (:value)"), {"value": value})
        return int(self._session.scalar(text("select count(*) from entries")) or 0)


async def main() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as session:
        session.execute(text("create table entries (value text not null)"))

        @provider()
        def ledger() -> Ledger:
            return Ledger(session)

        application = Agnara("dogfood_host")
        app = App("ledger")

        @app.capability
        def record(value: str, ledger: Ledger) -> int:
            return ledger.record(value)

        application.include(app)
        capabilities = application.compile()
        registry = DIRegistry()
        registry.bind(Ledger, ledger)
        container = DIContainer(registry)
        plan = ExecutionPlan.compile(capabilities["ledger.record"], registry)
        try:
            result = await invoke_result(
                plan,
                ExecutionContext(
                    Invocation(CapabilityId.parse("ledger.record"), {"value": "outside-core"}, {}),
                    container,
                ),
            )
            assert isinstance(result, Success) and result.value == 1
            session.commit()
            assert session.scalar(text("select count(*) from entries")) == 1
        finally:
            await container.aclose()

    engine.dispose()
    print("HOST_DOGFOOD_OK")


if __name__ == "__main__":
    asyncio.run(main())
