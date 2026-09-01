from agnara.capability.definition import CapabilityDefinition
from agnara.capability.identity import CapabilityId
from agnara.core.di.provider import Scope, provider
from agnara.core.di.registry import DIRegistry
from agnara.execution.plan import ExecutionPlan


class Database:
    pass


@provider(scope=Scope.SINGLETON)
def provide_db() -> Database:
    return Database()


def sample_handler(payload: dict, db: Database) -> str:
    return "ok"


def test_execution_plan_compilation():
    definition = CapabilityDefinition.declare(
        id=CapabilityId("test", "cap"), handler=sample_handler
    )

    registry = DIRegistry()
    registry.bind(Database, provide_db)

    plan = ExecutionPlan.compile(definition, registry)

    assert plan.definition is definition
    assert sample_handler in plan.target_deps
    assert plan.target_deps[sample_handler] == [Database]
