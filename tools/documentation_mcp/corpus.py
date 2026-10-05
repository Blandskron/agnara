"""Bounded, allowlisted startup loader and immutable documentation snapshot."""

from __future__ import annotations

import hashlib
import json
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any

MAX_SOURCE = 100 * 1024
MAX_CORPUS = 2 * 1024 * 1024
COMMIT = re.compile(r"[0-9a-f]{40}\Z")
IDENTITY = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,127}\Z")
TOKEN = re.compile(r"\w+", re.UNICODE)
STABILITIES = frozenset({"stable-api", "guidance", "current-repository", "proposed"})
NONBASELINE = frozenset({"current-repository", "proposed"})


class CorpusError(ValueError):
    """Only fixed categories may cross the startup or tool boundary."""

    def __init__(self, code: str = "stale_snapshot") -> None:
        self.code = code
        super().__init__(code)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def encode(value: Any) -> str:
    try:
        rendered = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
        rendered.encode("utf-8")
        return rendered
    except (ValueError, UnicodeError) as error:
        raise CorpusError() from error


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CorpusError()
        result[key] = value
    return result


def decode(data: bytes) -> Any:
    def reject_constant(_value: str) -> Any:
        raise CorpusError()

    try:
        return json.loads(
            data.decode("utf-8"), object_pairs_hook=_unique, parse_constant=reject_constant
        )
    except (ValueError, UnicodeError, RecursionError) as error:
        raise CorpusError() from error


def read_source(root: Path, name: str) -> bytes:
    """Read only canonical docs/examples; reject all links and Windows junctions."""
    path = PurePosixPath(name)
    if (
        not name
        or not re.fullmatch(r"[A-Za-z0-9_./-]+", name)
        or "\\" in name
        or ":" in name
        or "%" in name
        or path.is_absolute()
        or not path.parts
        or name != path.as_posix()
        or any(part in {".", ".."} or part.endswith((".", " ")) for part in path.parts)
        or path.parts[0] not in {"docs", "examples"}
        or path.suffix not in {".md", ".py", ".json"}
        or (path.suffix == ".json" and name not in {"docs/index.json", "docs/public-api.json"})
    ):
        raise CorpusError()
    try:
        current = root
        for part in (None, *path.parts):
            if part is not None:
                current /= part
            metadata = current.lstat()
            if stat.S_ISLNK(metadata.st_mode) or getattr(metadata, "st_file_attributes", 0) & 0x400:
                raise CorpusError()
        if not current.resolve().is_relative_to(root.resolve()) or not current.is_file():
            raise CorpusError()
        with current.open("rb") as source:
            data = source.read(MAX_SOURCE + 1)
        if len(data) > MAX_SOURCE:
            raise CorpusError("size_limit")
        data.decode("utf-8")
        return data
    except (OSError, UnicodeError) as error:
        raise CorpusError() from error


def read_index(root: Path) -> tuple[bytes, dict[str, Any], dict[str, bytes]]:
    raw = read_source(root, "docs/index.json")
    index = decode(raw)
    if (
        not isinstance(index, dict)
        or type(index.get("schema_version")) is not int
        or index["schema_version"] != 1
        or index.get("version") != "1.0.3"
        or not isinstance(index.get("release_commit"), str)
        or not COMMIT.fullmatch(index["release_commit"])
        or not isinstance(index.get("documents"), list)
        or not 1 <= len(index["documents"]) <= 256
    ):
        raise CorpusError()
    ids: set[str] = set()
    files = {"docs/index.json": raw}
    for entry in index["documents"]:
        if not isinstance(entry, dict):
            raise CorpusError()
        for field in ("id", "title", "path", "topic", "stability"):
            if not isinstance(entry.get(field), str) or not 1 <= len(entry[field]) <= 256:
                raise CorpusError()
            encode(entry[field])
        if (
            not IDENTITY.fullmatch(entry["id"])
            or not IDENTITY.fullmatch(entry["topic"])
            or entry["id"] in ids
            or entry["path"] in files
            or entry.get("version") != index["version"]
            or entry["stability"] not in STABILITIES
        ):
            raise CorpusError()
        ids.add(entry["id"])
        files[entry["path"]] = read_source(root, entry["path"])
        if sum(map(len, files.values())) > MAX_CORPUS:
            raise CorpusError("size_limit")
    if sum(entry["path"] == "docs/public-api.json" for entry in index["documents"]) != 1:
        raise CorpusError()
    return raw, index, files


def make_lock(root: Path, source_commit: str) -> bytes:
    """Offline preparation only; caller owns commit verification and lock review."""
    if not COMMIT.fullmatch(source_commit):
        raise CorpusError()
    _, index, files = read_index(root)
    return encode(
        {
            "schema_version": 1,
            "documentation_version": index["version"],
            "source_commit": source_commit,
            "release_commit": index["release_commit"],
            "sources": {name: digest(data) for name, data in sorted(files.items())},
        }
    ).encode("utf-8")


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    title: str
    path: str
    topic: str
    stability: str
    text: str
    sha256: str
    tokens: frozenset[str]
    associations_json: str


@dataclass(frozen=True, slots=True)
class Corpus:
    version: str
    source_commit: str
    release_commit: str
    sha256: str
    index_sha256: str
    documents: MappingProxyType[str, Document]
    modules: MappingProxyType[str, str]

    def envelope(self, document: Document | None, content: Any, truncated: bool = False) -> dict:
        path = "docs/index.json" if document is None else document.path
        return {
            "schema_version": 1,
            "documentation_version": self.version,
            "source_commit": self.source_commit,
            "release_commit": self.release_commit,
            "stability": "guidance" if document is None else document.stability,
            "source_path": path,
            "source_sha256": self.index_sha256 if document is None else document.sha256,
            "source_url": f"https://github.com/Blandskron/agnara/blob/{self.source_commit}/{path}",
            "content": content,
            "truncated": truncated,
        }


def load(root: Path, lock_bytes: bytes, expected_sha256: str) -> Corpus:
    """Verify pinned lock and every source before returning a frozen snapshot."""
    if len(lock_bytes) > MAX_SOURCE:
        raise CorpusError("size_limit")
    if digest(lock_bytes) != expected_sha256:
        raise CorpusError()
    lock = decode(lock_bytes)
    raw, index, files = read_index(root)
    if (
        not isinstance(lock, dict)
        or set(lock)
        != {"schema_version", "documentation_version", "source_commit", "release_commit", "sources"}
        or type(lock["schema_version"]) is not int
        or lock["schema_version"] != 1
        or lock["documentation_version"] != index["version"]
        or lock["release_commit"] != index["release_commit"]
        or not isinstance(lock["source_commit"], str)
        or not COMMIT.fullmatch(lock["source_commit"])
        or lock["sources"] != {name: digest(data) for name, data in sorted(files.items())}
    ):
        raise CorpusError()
    documents: dict[str, Document] = {}
    for entry in index["documents"]:
        text = files[entry["path"]].decode("utf-8")
        associations = {key: entry[key] for key in ("guide_ids", "test_ids") if key in entry}
        if any(
            not isinstance(values, list)
            or any(not isinstance(value, str) or not IDENTITY.fullmatch(value) for value in values)
            for values in associations.values()
        ):
            raise CorpusError()
        documents[entry["id"]] = Document(
            entry["id"],
            entry["title"],
            entry["path"],
            entry["topic"],
            entry["stability"],
            text,
            digest(files[entry["path"]]),
            frozenset(TOKEN.findall(f"{entry['title']} {entry['topic']} {text}".casefold())),
            encode(associations),
        )
    manifest = decode(files["docs/public-api.json"])
    modules: dict[str, str] = {}
    try:
        if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 3:
            raise CorpusError()
        if not isinstance(manifest["distributions"], list) or not manifest["distributions"]:
            raise CorpusError()
        for distribution in manifest["distributions"]:
            if not isinstance(distribution["modules"], list):
                raise CorpusError()
            for module in distribution["modules"]:
                name = module["module"]
                if not isinstance(name, str) or not IDENTITY.fullmatch(name) or name in modules:
                    raise CorpusError()
                seen: set[str] = set()
                if not isinstance(module["exports"], list):
                    raise CorpusError()
                for export in module["exports"]:
                    if (
                        not isinstance(export["name"], str)
                        or not export["name"].isidentifier()
                        or export["name"] in seen
                        or export["stability"] not in {"stable", "provisional", "deprecated"}
                    ):
                        raise CorpusError()
                    seen.add(export["name"])
                modules[name] = encode(module)
    except (KeyError, TypeError) as error:
        raise CorpusError() from error
    return Corpus(
        index["version"],
        lock["source_commit"],
        index["release_commit"],
        digest(lock_bytes),
        digest(raw),
        MappingProxyType(documents),
        MappingProxyType(modules),
    )
