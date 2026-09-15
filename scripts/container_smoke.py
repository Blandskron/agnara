"""Exercise an Agnara reference image through its public container boundary."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import time
import urllib.error
import urllib.request


def run(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *arguments], text=True, capture_output=True, check=check)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image")
    args = parser.parse_args()
    name = "agnara-container-smoke"
    run("rm", "-f", name, check=False)
    run(
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "-p",
        "127.0.0.1::8000",
        args.image,
    )
    try:
        inspection = json.loads(run("inspect", name).stdout)[0]
        assert inspection["Config"]["User"] == "agnara:agnara"
        port = run("port", name, "8000/tcp").stdout.strip().rsplit(":", 1)[-1]
        address = f"http://127.0.0.1:{port}"
        for _ in range(30):
            try:
                with urllib.request.urlopen(f"{address}/health", timeout=2) as response:
                    assert response.status == 200
                    assert json.load(response) == "ok"
                break
            except OSError:
                time.sleep(1)
        else:
            raise AssertionError(run("logs", name, check=False).stderr)

        with urllib.request.urlopen(f"{address}/openapi.json", timeout=2) as response:
            document = json.load(response)
        assert "/orders/{order_id}" in document["paths"]

        identity = run(
            "exec",
            name,
            "python",
            "-c",
            "import agnara, agnara_http; print(agnara.__file__, agnara_http.__file__)",
        )
        assert all("site-packages" in path for path in identity.stdout.split())
        assert run("exec", name, "id", "-u").stdout.strip() != "0"
        history = run("history", "--no-trunc", args.image).stdout
        assert re.search(r"(?i)(password|secret|token|api[_-]?key|private key)", history) is None
        assert run("exec", name, "test", "!", "-e", "/workspaces").returncode == 0
    finally:
        stopped = run("stop", "-t", "10", name, check=False)
        assert stopped.returncode in (0, 1), stopped.stderr
        run("rm", "-f", name, check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
