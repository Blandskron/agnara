from pathlib import Path

WORKSPACE_ROOT = Path(__file__).parents[2]
SMOKE_TEST = WORKSPACE_ROOT / "scripts" / "container_smoke.py"


def test_container_smoke_uses_a_reduced_runtime_privilege_set() -> None:
    source = SMOKE_TEST.read_text(encoding="utf-8")

    assert '"--cap-drop=ALL"' in source
    assert '"--security-opt=no-new-privileges"' in source
