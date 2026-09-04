"""Repository-wide packaging evidence for documentation UI assets (E6.19)."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tomllib
import zipfile
from importlib.resources import files
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_ROOT = WORKSPACE_ROOT / "packages" / "agnara-http"

PROVIDERS = {
    "swagger_ui": "5.32.14",
    "redoc": "2.5.3",
    "scalar": "1.67.0",
}


def test_every_documentation_asset_has_packaged_license_and_hash_evidence() -> None:
    vendor = files("agnara_http").joinpath("_vendor")

    for provider, version in PROVIDERS.items():
        root = vendor.joinpath(provider, version)
        manifest: dict[str, Any] = json.loads(
            root.joinpath("manifest.json").read_text(encoding="utf-8")
        )
        assert manifest["version"] == version
        assert root.joinpath("LICENSE").read_text(encoding="utf-8").strip()
        assert manifest["assets"]

        for name, evidence in manifest["assets"].items():
            body = root.joinpath(*name.split("/")).read_bytes()
            assert len(body) == evidence["bytes"]
            assert hashlib.sha256(body).hexdigest() == evidence["sha256"]
            assert evidence["sri"].startswith("sha384-")


def test_built_wheel_contains_the_complete_verified_resource_tree(tmp_path: Path) -> None:
    project = tomllib.loads((PACKAGE_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/agnara_http"]
    assert project["project"]["dependencies"] == ["agnara"]

    uv = shutil.which("uv")
    assert uv is not None, "the documented release tool must be available"
    completed = subprocess.run(
        [uv, "build", "--package", "agnara-http", "--out-dir", str(tmp_path)],
        cwd=WORKSPACE_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr

    wheel = next(tmp_path.glob("*.whl"))
    source_root = PACKAGE_ROOT / "src"
    expected = {
        path.relative_to(source_root).as_posix()
        for path in (source_root / "agnara_http" / "_vendor").rglob("*")
        if path.is_file()
    }
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        assert expected <= names
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
        dependencies = [line for line in metadata.splitlines() if line.startswith("Requires-Dist:")]
        assert dependencies == ["Requires-Dist: agnara"]

    assert expected
    assert all(path.startswith("agnara_http/_vendor/") for path in expected)
