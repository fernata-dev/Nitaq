"""D2: normaliser + multilingual concept scanner.

Pipeline: d2_normalizer.views(text) produces normalised token views (base,
de-spaced, de-leeted, ROT13, decoded Base64, tag-smuggled).  Each view is
matched against the concept lexicon (d2_lexicon) with script-aware matchers:
  * English: exact word / prefix / phrase
  * Arabic script: clitic stripping (و ف ب ل ال لل) + pronoun suffixes
  * Latin script vs Arabizi entries: consonant skeleton (2 3 5 7 9 -> sounds)
  * Latin script vs Arabic entries: derived Arabizi skeleton (cross-script)
Concept hits are combined by proximity rules into weighted evidence; the
best view's score (+1 if the evidence was hidden) is compared to a threshold.

FROZEN at git tag `freeze-scanner`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache

from nitaq_bench.defenses import d2_lexicon as L
from nitaq_bench.defenses import d2_normalizer as N
from nitaq_bench.defenses.base import Defense, ScreenVerdict
from nitaq_bench.defenses.d1_keyword import _OVERRIDE_RE

_AR = re.compile(r"[ء-ي]")
_PROCLITIC_1 = ("و", "ف")                      # و ف
_ARTICLES = ("ال", "لل")              # ال لل
_PREP = ("ب", "ل", "ك")                    # ب ل ك
_SUFFIXES = ("ه", "ها", "هم", "ك", "كم", "ي",
             "ني", "نا", "لي", "لك")
_AZ_PROCLITIC_SK = ("wl", "bl", "fl", "w", "l", "b", "f")


def _ar_forms(tok: str) -> set[str]:
    forms = {tok}
    for f in list(forms):
        if f.startswith(_PROCLITIC_1) and len(f) >= 3:
            forms.add(f[1:])
    for f in list(forms):
        for pre in _PREP:
            if f.startswith(pre + "ال") and len(f) > 5:
                forms.add(f[3:])
            elif f.startswith(pre) and len(f) > 3:
                forms.add(f[1:])
    for f in list(forms):
        for art in _ARTICLES:
            if f.startswith(art) and len(f) > 3:
                forms.add(f[2:])
    return forms


def _ar_word_match(tok: str, pat: str) -> bool:
    forms = _ar_forms(tok)
    if pat.endswith("*"):
        stem = pat[:-1]
        return any(f.startswith(stem) for f in forms)
    if pat in forms:
        return True
    return any(f == pat + s for f in forms for s in _SUFFIXES)


@lru_cache(maxsize=4096)
def _derived_skeleton(word: str) -> str:
    """Arabic-script entry -> Egyptian-Arabizi consonant skeleton."""
    w = word.rstrip("*")
    for art in _ARTICLES:
        if w.startswith(art) and len(w) > 3:
            w = w[2:]
    out = []
    for i, ch in enumerate(w):
        if ch == "و":
            out.append("w" if i == 0 or (i + 1 < len(w) and w[i + 1] == "ا") else "")
        elif ch == "ي":
            out.append("y" if i == 0 else "")
        else:
            out.append(L.AR_TO_SKELETON.get(ch, ""))
    return re.sub(r"(.)\1+", r"\1", "".join(out))


def _sk_variants(sk: str) -> set[str]:
    out = {sk}
    for pre in _AZ_PROCLITIC_SK:
        if sk.startswith(pre) and len(sk) - len(pre) >= 3:
            out.add(sk[len(pre):])
    return out


@dataclass(frozen=True)
class _Pat:
    concept: str
    script: str            # en | ar | az
    words: tuple[str, ...]
    sk: tuple[str, ...]    # skeletons for az words / derived skeletons for ar words


def _compile() -> list[_Pat]:
    pats = []
    for concept, by in L.CONCEPTS.items():
        for script, entries in by.items():
            for e in entries:
                words = tuple(N.fold(w) if script != "az" else w.lower() for w in e.split())
                if script == "az":
                    sk = tuple(N.skeleton(w) for w in words)
                elif script == "ar":
                    sk = tuple(_derived_skeleton(w) for w in words)
                else:
                    sk = ()
                pats.append(_Pat(concept, script, words, sk))
    return pats


PATTERNS = _compile()


def _word_match(tok: N.Tok, pat: _Pat, i: int, lossy: bool) -> bool:
    w = pat.words[i]
    t = tok.text
    if tok.address:
        return False
    if _AR.search(t):
        return pat.script == "ar" and _ar_word_match(t, w)
    # Latin-script token
    if pat.script == "en":
        return t.startswith(w[:-1]) if w.endswith("*") else t == w
    if pat.script == "az" and t == w.replace("'", ""):
        return True
    sk = pat.sk[i] if pat.sk else ""
    if not sk or len(sk) < 3 or not tok.sk:
        return False
    if pat.script == "ar" and len(sk) < 4 and len(pat.words) == 1:
        return False  # short derived skeletons collide with English words
    variants = _sk_variants(tok.sk)
    if sk in variants:
        return True
    if lossy:
        lsk = N.lossy(sk)
        return len(lsk) >= 3 and any(N.lossy(v) == lsk for v in variants)
    return False


def _blob_hit(tok: N.Tok, pat: _Pat) -> bool:
    if not tok.blob or len(pat.words) != 1:
        return False
    w = pat.words[0].rstrip("*")
    if pat.script == "en":
        return len(w) >= 5 and w in tok.text
    if pat.script == "ar":
        return len(w) >= 4 and w in tok.text
    return False


def concept_hits(view: N.View) -> dict[str, list[int]]:
    """concept -> token positions where a lexicon pattern ENDS (last word of a phrase)."""
    hits: dict[str, list[int]] = {}
    toks = view.tokens
    for i in range(len(toks)):
        for p in PATTERNS:
            n = len(p.words)
            if i + n > len(toks):
                continue
            if all(_word_match(toks[i + j], p, j, view.lossy) for j in range(n)) or _blob_hit(toks[i], p):
                hits.setdefault(p.concept, []).append(i + n - 1)
    for k in hits:
        hits[k] = sorted(set(hits[k]))
    return hits


def _near(a: list[int], b: list[int], window: int, ordered: bool) -> tuple[int, int] | None:
    for i in a:
        for j in b:
            d = j - i
            if (0 < d <= window) if ordered else (0 < abs(d) <= window):
                return i, j
    return None


def score_view(view: N.View) -> tuple[int, list[dict]]:
    h = concept_hits(view)
    toks = view.tokens
    get = lambda c: h.get(c, [])
    reasons: list[dict] = []

    def add(rule: str, *pos: int) -> None:
        if any(r["rule"] == rule for r in reasons):
            return
        ev = " ".join(toks[p].text for p in sorted(set(pos)))
        reasons.append({"rule": rule, "weight": L.WEIGHTS[rule], "view": view.name, "evidence": ev})

    m = _near(get("IGNORE"), get("INSTR"), L.WINDOWS["override"], ordered=True)
    if m:
        add("override", *m)
    secret_pos = set(get("SECRET"))
    for i in get("NEG_TELL"):
        for j in get("AUDIENCE"):
            if 0 < j - i <= L.WINDOWS["conceal"] and not any(i < s < j for s in secret_pos):
                add("conceal", i, j)
    m = _near(get("SEND"), get("SECRET"), L.WINDOWS["secret_send"], ordered=False) or \
        _near(get("ACCESS"), get("SECRET"), L.WINDOWS["secret_access"], ordered=True)
    if m:
        add("secret_flow", *m)
    m = _near(get("CHANGE"), get("ADDRESS_NOUN"), L.WINDOWS["change_address"], ordered=False) or \
        _near(get("SEND"), get("INSTEAD"), L.WINDOWS["instead"], ordered=True)
    if m:
        add("redirect", *m)
    addr = [k for k, t in enumerate(toks) if t.address]
    m = _near(get("SEND"), addr, L.WINDOWS["send_address"], ordered=True)
    if m:
        add("send_to_address", *m)
    if get("AI_ADDR"):
        add("ai_addressed", get("AI_ADDR")[0])
    joined = " ".join(t.text for t in toks)
    mm = _OVERRIDE_RE.search(joined)
    if mm:
        reasons.append({"rule": "d1_override", "weight": L.WEIGHTS["d1_override"],
                        "view": view.name, "evidence": mm.group(0)})
    # override and d1_override describe the same evidence: count it once
    names = {r["rule"] for r in reasons}
    total = sum(r["weight"] for r in reasons
                if not (r["rule"] == "d1_override" and "override" in names))
    return total, reasons


_INVISIBLE_IN_WORD = re.compile(r"\w[" + N.ZERO_WIDTH.replace("‍", "") + N.BIDI_CONTROLS + r"]+\w")


class D2Scanner(Defense):
    name = "D2"
    kind = "scanner"
    description = ("Normaliser (NFKC, invisible chars, Arabic letter forms, diacritics, tatweel, "
                   "look-alikes, de-leet, de-space, ROT13, Base64, tag smuggling) + concept lexicon "
                   "in en/msa/arz/arabizi with Arabizi skeleton and cross-script matching.")

    def screen(self, text: str, source: str) -> ScreenVerdict:
        best_score, best_reasons, best_view = 0, [], "base"
        base_score = None
        for view in N.views(text):
            s, r = score_view(view)
            if view.name == "base":
                base_score = s
            if s > best_score:
                best_score, best_reasons, best_view = s, r, view.name
        hidden = []
        if best_score and best_view != "base" and best_score > (base_score or 0):
            hidden.append({"rule": "hidden_text", "weight": L.WEIGHTS["hidden_text"], "view": best_view,
                           "evidence": f"evidence only visible after undoing: {best_view}"})
        elif _INVISIBLE_IN_WORD.search(text) or N._TAG_RE.search(text):
            hidden.append({"rule": "hidden_text", "weight": L.WEIGHTS["hidden_text"], "view": "raw",
                           "evidence": "invisible characters inside words"})
        if best_score:
            best_score += sum(h["weight"] for h in hidden)
            best_reasons = best_reasons + hidden
        return ScreenVerdict(best_score >= L.FLAG_THRESHOLD, float(best_score), best_reasons, self.name)
