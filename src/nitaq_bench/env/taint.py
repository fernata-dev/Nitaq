"""Value-level taint tracking (deliberately simple and language-blind).

A string value is *tainted* when it occurs verbatim inside untrusted content
that was delivered to the agent AND does not occur in any trusted string
(the user's instruction or the task manifest).  This is byte-for-byte
matching: it never interprets, normalises or decodes text.  Consequence
(measured, not hidden): if untrusted content carries a destination in an
encoded form, the decoded value is NOT recognised as tainted.
"""
from __future__ import annotations


class TaintTracker:
    def __init__(self, trusted: list[str] | None = None) -> None:
        self._trusted: list[str] = [t for t in (trusted or []) if t]
        self._untrusted: list[str] = []

    def add_trusted(self, text: str) -> None:
        if text:
            self._trusted.append(text)

    def add_untrusted(self, text: str) -> None:
        if text:
            self._untrusted.append(text)

    def is_tainted(self, value: object) -> bool:
        if not isinstance(value, str) or len(value) < 3:
            return False
        if any(value in t for t in self._trusted):
            return False
        return any(value in u for u in self._untrusted)


# ---------------------------------------------------------------------------
# m13: normalised taint (used by D6 and by Nitaq's taint mode).
# Still language-blind: it never interprets meaning.  It only undoes the
# character-level obfuscations measured in this project (invisible
# characters, look-alike letters, Arabic letter forms, spacing, leet, ROT13,
# Base64) using the FROZEN D2 normaliser functions, then matches values.
# Designed after the D5-taint numbers were visible on dev (m3) AND test (m6):
# its test-split result is not a clean held-out evaluation.

_LEET_DIGITS = {"4": "a", "3": "e", "1": "i", "0": "o", "5": "s", "7": "t"}


def canonical(text: str) -> str:
    from nitaq_bench.defenses import d2_normalizer as N

    return " ".join(N.fold(text).split())


def canonical_views(text: str, depth: int = 0) -> list[str]:
    """The canonical text plus every decoded / de-obfuscated view of it."""
    import codecs

    from nitaq_bench.defenses import d2_normalizer as N

    base = canonical(text)
    views = [base, canonical(N.despace(base)), canonical(codecs.encode(base, "rot_13")),
             " ".join(N.deleet_token(t) for t in base.split()),
             # the frozen de-leet skips address-like tokens; undo leet digits everywhere,
             # keeping '@' and '$' literal so addresses survive (dev observation, m13)
             "".join(_LEET_DIGITS.get(c, c) for c in base)]
    _, smuggled = N.strip_invisible(text)
    if smuggled:
        views.append(canonical(smuggled))
    if depth < 2:
        for dec in N.decode_b64_candidates(N.strip_invisible(text)[0]):
            views.extend(canonical_views(dec, depth + 1))
    return list(dict.fromkeys(v for v in views if v))


class TaintOracle:
    """Callable byte-exact oracle (D5) that also answers the normalised question (D6).

    Guards receive only this object, never the content itself.
    """

    def __init__(self, tracker: TaintTracker) -> None:
        self._t = tracker
        self._cache: dict[int, list[str]] = {}

    def __call__(self, value: object) -> bool:
        return self._t.is_tainted(value)

    def normalized(self, value: object) -> bool:
        if not isinstance(value, str) or len(value) < 3:
            return False
        v = canonical(value)
        if any(v in canonical(t) for t in self._t._trusted):
            return False
        for i, u in enumerate(self._t._untrusted):
            if i not in self._cache:
                self._cache[i] = canonical_views(u)
            if any(v in view for view in self._cache[i]):
                return True
        return False
