"""Small shared helpers: project root, git provenance, JSON/JSONL IO, digests."""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import subprocess
import zlib
from pathlib import Path
from typing import Any, Iterable

DEFAULT_SEED = 1337


def project_root() -> Path:
    """Root of the checkout (the folder holding data/ and src/)."""
    env = os.environ.get("NITAQ_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    cand = here.parents[2]
    if (cand / "data").is_dir():
        return cand
    cwd = Path.cwd()
    if (cwd / "data").is_dir():
        return cwd
    return cand


def stable_int(*parts: Any) -> int:
    """Deterministic 32-bit integer from arbitrary parts (never Python's hash())."""
    return zlib.crc32("\x1f".join(str(p) for p in parts).encode("utf-8")) & 0xFFFFFFFF


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=project_root(), capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def git_info() -> dict:
    commit = _git("rev-parse", "HEAD")
    # only uncommitted changes that can change results count (generated outputs do not)
    status = _git("status", "--porcelain", "--", "src", "data", "pyproject.toml", "nitaq_bench.py")
    tags = _git("tag", "--points-at", "HEAD")
    return {
        "commit": commit or "unknown",
        "dirty": bool(status) if status is not None else None,
        "dirty_scope": "src/, data/, pyproject.toml, nitaq_bench.py",
        "tags_at_head": tags.split("\n") if tags else [],
    }


def runtime_info() -> dict:
    from nitaq_bench import __version__

    return {
        "nitaq_bench_version": __version__,
        "python": platform.python_version(),
        "platform": platform.system(),
    }


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
    return rows


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2, sort_keys=False)
        fh.write("\n")


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def canonical_digest(obj: Any) -> str:
    """sha256 over canonical JSON; used to compare runs independent of date/commit."""
    blob = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_csv(path: Path, header: list[str], rows: Iterable[Iterable[Any]]) -> None:
    import csv

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(header)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])
