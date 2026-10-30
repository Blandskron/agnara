"""Run the same public consumer used by the installed candidate-wheel lane."""

import asyncio

import pytest

from tests.reference_apps.nested_resource_lifecycle import CASES, Case, run_case


@pytest.mark.parametrize("case", CASES)
def test_nested_resource_lifecycle(case: Case) -> None:
    asyncio.run(run_case(case))
