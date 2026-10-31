"""Read-only checks of manifest intent and installed distribution metadata."""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version

from agnara_cli._apps import _manifest as load_project_manifest
from agnara_cli._command import CommandResult
from agnara_cli._manifest import ManifestError, ProjectManifest

_ADAPTERS = {"http": "agnara-http", "mcp": "agnara-mcp"}
_UNCHECKED_EXPOSURE_MESSAGES = {
    "a2a": "adapter metadata checks are not implemented for this declared exposure",
    "events": "reserved namespace; no implemented Agnara event runtime",
    "tasks": "no implemented Agnara task runtime",
}
_UNCHECKED = (
    "project_python_constraint",
    "application_imports",
    "runtime_registration",
    "dependency_cycles",
    "protocol_configuration",
    "architecture_rules",
    "transitive_dependencies",
)


def add_doctor_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    parser = subparsers.add_parser(
        "doctor",
        help="check manifest, app paths and adapter metadata without running project code",
        description=(
            "Read-only static checks. No project or adapter code is imported; "
            "runtime registration, graph cycles and protocol behavior are not checked."
        ),
    )
    parser.add_argument("--project", metavar="DIR", help="directory to search and its ancestors")
    parser.add_argument("--json", action="store_true", help="emit a versioned diagnostic report")
    parser.set_defaults(handler=run_doctor)


def _python_version() -> tuple[int, int, int]:
    return sys.version_info[:3]


def _distribution_check(
    name: str,
    checks: list[dict[str, str]],
    *,
    kernel: str | None = None,
    compare: bool = False,
) -> str | None:
    try:
        installed = version(name)
    except PackageNotFoundError:
        checks.append({"id": f"distribution:{name}", "status": "fail", "message": "not installed"})
        return None
    if not isinstance(installed, str) or not installed.strip():
        checks.append(
            {
                "id": f"distribution:{name}",
                "status": "fail",
                "message": "installed metadata has no non-empty version",
            }
        )
        return None
    status = "pass"
    message = f"installed {installed}"
    if compare and kernel is None:
        status, message = "fail", "cannot compare versions without installed agnara metadata"
    elif compare and installed != kernel:
        status, message = "fail", f"installed {installed}; expected kernel version {kernel}"
    checks.append({"id": f"distribution:{name}", "status": status, "message": message})
    return installed


def _app_checks(manifest: ProjectManifest, checks: list[dict[str, str]]) -> None:
    assert manifest.source is not None
    root = manifest.source.parent.resolve()
    for app in manifest.apps:
        status = "pass"
        message = f"directory exists: {app.path}"
        try:
            destination = (root / app.path).resolve()
            if not destination.is_relative_to(root):
                status, message = "fail", f"directory escapes project: {app.path}"
            elif not destination.is_dir():
                status, message = "fail", f"directory is missing or inaccessible: {app.path}"
        except OSError, RuntimeError:
            status, message = "fail", f"cannot resolve app directory: {app.path}"
        checks.append({"id": f"app:{app.name}:path", "status": status, "message": message})


def run_doctor(arguments: argparse.Namespace) -> CommandResult:
    checks: list[dict[str, str]] = []
    interpreter = _python_version()
    checks.append(
        {
            "id": "python",
            "status": "pass" if interpreter >= (3, 14) else "fail",
            "message": f"executing Python {'.'.join(map(str, interpreter))}; requires >=3.14",
        }
    )
    manifest = None
    try:
        manifest = load_project_manifest(arguments)
        checks.append({"id": "manifest", "status": "pass", "message": "valid agnara.toml"})
    except ManifestError as error:
        checks.append({"id": "manifest", "status": "fail", "message": str(error)})

    kernel = _distribution_check("agnara", checks)
    _distribution_check("agnara-cli", checks, kernel=kernel, compare=True)
    unchecked = list(_UNCHECKED)
    project = None
    if manifest is None:
        unchecked.extend(("declared_app_paths", "declared_adapters"))
    else:
        project = {"name": manifest.name, "python": manifest.python}
        _app_checks(manifest, checks)
        exposures = dict.fromkeys(exposure for app in manifest.apps for exposure in app.exposures)
        for exposure in exposures:
            distribution = _ADAPTERS.get(exposure)
            if distribution is None:
                checks.append(
                    {
                        "id": f"exposure:{exposure}",
                        "status": "fail",
                        "message": _UNCHECKED_EXPOSURE_MESSAGES[exposure],
                    }
                )
            else:
                _distribution_check(distribution, checks, kernel=kernel, compare=True)

    status = "fail" if any(check["status"] == "fail" for check in checks) else "pass"
    report = {
        "format": "agnara.doctor",
        "format_version": 1,
        "project": project,
        "checks": checks,
        "status": status,
        "unchecked": unchecked,
    }
    if arguments.json:
        output = json.dumps(report, indent=2, sort_keys=True)
    else:
        label = manifest.name if manifest is not None else "unknown project"
        lines = [f"doctor {label}: {status}"]
        lines.extend(f"[{check['status']}] {check['id']}: {check['message']}" for check in checks)
        lines.append("Unchecked: " + ", ".join(unchecked))
        output = "\n".join(lines)
    return CommandResult(output, 1 if status == "fail" else 0)
