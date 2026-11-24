"""Check that the content scanners are byte-identical to git tag `freeze-scanner`.

HARD RULE 4: scanners are developed on the dev split only and frozen before
any run on the test split.  This module makes that checkable by a machine.
"""
from __future__ import annotations

import hashlib
import json
import subprocess

from nitaq_bench.util import project_root

RECORDED_CHANGES = "docs/post_freeze_changes.json"


def recorded_changes() -> list[dict]:
    p = project_root() / RECORDED_CHANGES
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def rename_record() -> dict | None:
    """The recorded package rename (m21), if any.  Its `names_now_to_freeze` pairs map the
    current names back to the names the files had at the freeze tag; a frozen file that is
    byte-identical to the tag after that mapping differs from it only by the name."""
    for c in recorded_changes():
        if c.get("kind") == "rename":
            return c
    return None


def to_freeze_names(data, rec: dict | None):
    if not rec:
        return data
    for now, then in rec["names_now_to_freeze"]:
        if isinstance(data, bytes):
            data = data.replace(now.encode(), then.encode())
        else:
            data = data.replace(now, then)
    return data

FREEZE_TAG = "freeze-scanner"
FROZEN_FILES = (
    "src/nitaq_bench/attacks/encoders.py",       # removing an encoding a scanner fails on would also be rigging
    "src/nitaq_bench/defenses/d1_keyword.py",
    "src/nitaq_bench/defenses/d2_normalizer.py",
    "src/nitaq_bench/defenses/d2_lexicon.py",
    "src/nitaq_bench/defenses/d2_scanner.py",
    "src/nitaq_bench/defenses/d3_llm_judge.py",
    "src/nitaq_bench/defenses/d4_cpt.py",
)


def _git(*args: str) -> tuple[int, bytes]:
    try:
        p = subprocess.run(["git", *args], cwd=project_root(), capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return 1, b""
    return p.returncode, p.stdout


PINNED_TAGS = "docs/tags.json"
FREEZE_MANIFEST = "docs/freeze_manifest.json"


def freeze_manifest() -> dict | None:
    """sha256 of the frozen files at the freeze tag, for clones that do not carry the git history."""
    p = project_root() / FREEZE_MANIFEST
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def pinned_tags() -> dict:
    p = project_root() / PINNED_TAGS
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8")).get("tags", {})


def freeze_status() -> dict:
    root = project_root()
    code, out = _git("rev-parse", "--verify", "--quiet", f"refs/tags/{FREEZE_TAG}^{{commit}}")
    ref = FREEZE_TAG
    pinned = pinned_tags().get(FREEZE_TAG, {}).get("commit")
    status: dict = {"tag": FREEZE_TAG, "tag_exists": code == 0,
                    "tag_commit": out.decode().strip() if code == 0 else None,
                    "pinned_commit": pinned, "files": {}, "ok": False}
    if code == 0 and pinned and status["tag_commit"] != pinned:
        status["reason"] = f"tag {FREEZE_TAG} points to {status['tag_commit']} but {PINNED_TAGS} pins {pinned}: the tag was moved"
        return status
    manifest = None
    if code != 0:
        if not pinned or _git("cat-file", "-e", f"{pinned}^{{commit}}")[0] != 0:
            manifest = freeze_manifest()
            if not manifest:
                status["reason"] = "freeze tag not found and no pinned freeze commit available"
                return status
            status["resolved_via"] = FREEZE_MANIFEST       # a clone without the history: compare hashes
        else:
            ref = pinned
            status["resolved_via"] = PINNED_TAGS
    all_same = True
    recorded = {(c["file"], c["sha256"]): c for c in recorded_changes() if c.get("kind") != "rename"}
    ren = rename_record()
    renamed = False
    status["post_freeze_changes"] = []
    for rel in FROZEN_FILES:
        if manifest is not None:
            c, blob = (0, None) if rel in manifest["files"] else (1, b"")
        else:
            c, blob = _git("show", f"{ref}:{to_freeze_names(rel, ren)}")
        path = root / rel
        if c != 0:
            same = False
            note = "not present at freeze tag"
        elif not path.exists():
            same = False
            note = "missing in working tree"
        else:
            data = path.read_bytes()
            if manifest is not None:
                want = manifest["files"][rel]
                same = hashlib.sha256(data).hexdigest() == want
                note = "identical (sha256 = freeze manifest)" if same else "CHANGED since freeze"
                if not same and ren and hashlib.sha256(to_freeze_names(data, ren)).hexdigest() == want:
                    same, renamed = True, True
                    note = "identical except the package name (sha256 of the freeze-time bytes)"
            else:
                same = data == blob
                note = "identical" if same else "CHANGED since freeze"
            if not same and manifest is None and ren and to_freeze_names(data, ren) == blob:
                same, renamed = True, True
                note = "identical except the package name (checked byte for byte)"
            if not same:
                rec = recorded.get((rel, hashlib.sha256(to_freeze_names(data, ren)).hexdigest()))
                if rec:
                    note = "changed after freeze (recorded: " + rec["reason"][:60] + "...)"
                    status["post_freeze_changes"].append(rec)
                    status["files"][rel] = {"same": False, "recorded": True, "note": note}
                    continue
        status["files"][rel] = {"same": same, "note": note}
        all_same = all_same and same
    if renamed:      # the name map stays in docs/post_freeze_changes.json; results only list the change
        status["post_freeze_changes"].append({k: v for k, v in ren.items() if k != "names_now_to_freeze"})
    status["ok"] = all_same
    status["identical_to_tag"] = all_same and not status["post_freeze_changes"]
    if not all_same:
        status["reason"] = ("frozen files differ from the freeze tag and the change is not recorded in "
                            f"{RECORDED_CHANGES}; see CHANGELOG.md")
    return status


def restore_tags() -> int:
    """Recreate missing tags locally from docs/tags.json (never pushes anything)."""
    made = 0
    for name, t in pinned_tags().items():
        if _git("rev-parse", "--verify", "--quiet", f"refs/tags/{name}")[0] == 0:
            print(f"{name}: exists")
            continue
        if _git("cat-file", "-e", f"{t['commit']}^{{commit}}")[0] != 0:
            print(f"{name}: commit {t['commit'][:10]} not in this clone (fetch full history)")
            continue
        args = ["tag", "-a", name, "-m", t["message"] or name, t["commit"]] if t.get("annotated") else ["tag", name, t["commit"]]
        code, _ = _git(*args)
        print(f"{name}: {'created' if code == 0 else 'FAILED'} at {t['commit'][:10]}")
        made += code == 0
    return 0
