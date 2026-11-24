import hashlib
import os
from pathlib import Path

SECRETS = ("ghp_FAKEFAKEFAKEFAKEFAKEFAKEFAKE00", "sk-FAKEFAKEFAKEFAKEFAKEFAKE", "Bearer FAKE-TOKEN-nitaq",
           "FAKE KEY FOR TESTS")


def tree_digest(root: Path, exclude: str | None = None) -> dict:
    out = {}
    for p in sorted(Path(root).rglob("*")):
        if exclude and exclude in p.parts:
            continue
        if p.is_file() and not p.is_symlink():
            st = p.stat()
            out[str(p.relative_to(root))] = (hashlib.sha256(p.read_bytes()).hexdigest(), st.st_mtime_ns, st.st_size)
    return out


def env_with_src() -> dict:
    src = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ)
    env["PYTHONPATH"] = src + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env
