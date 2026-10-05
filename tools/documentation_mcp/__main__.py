"""Explicit offline lock preparation or a read-only local stdio host."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .corpus import MAX_SOURCE, CorpusError, digest, load, make_lock


async def serve(root: Path, lock: Path, expected: str) -> None:
    # Operator-selected lock is separate from all client-visible corpus IDs.
    with lock.open("rb") as source:
        lock_bytes = source.read(MAX_SOURCE + 1)
    corpus = load(root, lock_bytes, expected)
    from mcp.server.stdio import stdio_server

    from .server import build_server

    server = build_server(corpus)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Offline setup; prints a lock, never writes it")
    prepare.add_argument("--root", type=Path, required=True)
    prepare.add_argument("--source-commit", required=True)
    host = commands.add_parser("serve", help="Run a pinned read-only snapshot over stdio")
    host.add_argument("--root", type=Path, required=True)
    host.add_argument("--lock", type=Path, required=True)
    host.add_argument("--lock-sha256", required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            lock = make_lock(args.root, args.source_commit)
            sys.stdout.write(lock.decode("utf-8"))
            sys.stderr.write(f"lock_sha256={digest(lock)}\n")
        else:
            asyncio.run(serve(args.root, args.lock, args.lock_sha256))
    except CorpusError, OSError:
        sys.stderr.write("Documentation snapshot refused: stale_snapshot or size_limit\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
