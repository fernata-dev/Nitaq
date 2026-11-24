"""D2 part 1: text normaliser.  Turns one raw text into several "views".

A view is a list of tokens after undoing one family of obfuscation:
  base      NFKC, invisible characters removed, Arabic letter forms folded,
            diacritics/tatweel stripped, look-alike letters folded, lower-cased,
            elongation collapsed
  despaced  "i g n o r e" style spaced letters joined back into words
  deleet    4->a 3->e 1->i 0->o 5->s 7->t inside mixed letter/digit tokens
  rot13     ROT13 applied to Latin letters
  b64:N     text decoded from a Base64-looking run (appended, then normalised again)
  tags      text smuggled in Unicode tag characters (U+E0020..U+E007E)
Each token also carries an Arabizi consonant skeleton (digits 2 3 5 6 7 8 9
mapped to their Arabic sounds, vowels dropped, repeats collapsed).

This module never decides anything; d2_scanner.py does.
FROZEN at git tag `freeze-scanner`.
"""
from __future__ import annotations

import base64
import binascii
import codecs
import re
import unicodedata
from dataclasses import dataclass

ZERO_WIDTH = "​‌‍⁠﻿­᠎͏"
BIDI_CONTROLS = "‎‏‪‫‬‭‮⁦⁧⁨⁩؜"
_INVISIBLE_RE = re.compile("[" + ZERO_WIDTH + BIDI_CONTROLS + "]")
_TAG_RE = re.compile("[\U000e0000-\U000e007f]+")
_DIACRITICS_RE = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_ELONGATION_RE = re.compile(r"([^\W\d_])\1{2,}")

ARABIC_FOLD = str.maketrans({
    "آ": "ا", "أ": "ا", "إ": "ا", "ٱ": "ا",  # آأإٱ -> ا
    "ى": "ي", "ی": "ي", "ے": "ي", "ې": "ي",  # ى ی ے -> ي
    "ة": "ه", "ھ": "ه", "ہ": "ه", "ە": "ه",  # ة ھ ہ ە -> ه
    "ۀ": "ه",
    "ؤ": "و", "ئ": "ي",                                          # ؤ -> و, ئ -> ي
    "ک": "ك", "گ": "ك",                                          # ک گ -> ك
    "پ": "ب", "چ": "ج", "ڤ": "ف",                      # پ چ ڤ
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
})

# Cyrillic / Greek letters that look like Latin letters.
HOMOGLYPH_FOLD = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x",
    "у": "y", "і": "i", "ј": "j", "ѕ": "s", "һ": "h", "ԁ": "d",
    "А": "a", "Е": "e", "О": "o", "Р": "p", "С": "c", "Х": "x",
    "І": "i", "В": "b", "Н": "h", "К": "k", "М": "m", "Т": "t",
    "ο": "o", "α": "a", "ε": "e", "ι": "i", "κ": "k", "ν": "v",
    "ρ": "p", "τ": "t", "υ": "u", "χ": "x",
})

LEET_FOLD = {"4": "a", "3": "e", "1": "i", "0": "o", "5": "s", "7": "t", "@": "a", "$": "s"}

_B64_RE = re.compile(r"(?<![A-Za-z0-9+/=_-])[A-Za-z0-9+/_-]{16,}={0,2}")
_SENT_END = ".!?;:؟؛۔"
_STRIP_CHARS = "\"'`.,!?;:()[]{}<>|*#~^،؛؟۔«»“”‘’…-_=/\\"
_DETACHED_ARTICLES = {"ال", "لل", "بال", "فال",
                      "وال", "كال"}
_ARABIZI_DIGITS = set("2356789")
_DIGRAPHS = (("3'", "G"), ("7'", "K"), ("kh", "K"), ("gh", "G"), ("sh", "X"), ("ch", "X"),
             ("th", "t"), ("dh", "d"), ("ph", "f"))
_AZ_DIGIT = {"2": "", "3": "E", "5": "K", "6": "t", "7": "h", "8": "G", "9": "s"}
_LOSSY = str.maketrans({"E": None, "K": "S", "s": "S", "h": "T", "t": "T"})


@dataclass
class Tok:
    text: str                 # normalised token, apostrophes removed
    sent: int                 # sentence index
    sk: str = ""              # Arabizi skeleton ("" for non-Latin tokens)
    sk_lossy: str = ""        # skeleton with leet/Arabizi digit ambiguity merged
    az_digit: bool = False    # token (before de-leet) contains an Arabizi digit
    address: bool = False     # looks like an e-mail address or URL
    blob: bool = False        # long token produced by joining spaced letters


@dataclass
class View:
    name: str
    tokens: list[Tok]
    lossy: bool = False       # match Arabizi on the lossy skeleton (de-leeted text)


# ----------------------------------------------------------------- folding
def strip_invisible(text: str) -> tuple[str, str]:
    """Remove zero-width/bidi characters.  Returns (clean_text, tag_smuggled_text)."""
    smuggled = "".join(
        chr(ord(ch) - 0xE0000) for m in _TAG_RE.finditer(text) for ch in m.group(0)
        if 0xE0020 <= ord(ch) <= 0xE007E
    )
    text = _TAG_RE.sub("", text)
    return _INVISIBLE_RE.sub("", text), smuggled


def fold(text: str) -> str:
    """NFKC + invisible removal + Arabic/homoglyph folding + lower-case + elongation collapse."""
    text = unicodedata.normalize("NFKC", text)
    text, _ = strip_invisible(text)
    text = _DIACRITICS_RE.sub("", text)
    text = text.translate(ARABIC_FOLD).translate(HOMOGLYPH_FOLD)
    text = text.replace("’", "'").replace("‘", "'").replace("ʼ", "'").lower()
    return _ELONGATION_RE.sub(r"\1", text)


def skeleton(token: str) -> str:
    """Arabizi consonant skeleton of a Latin-script token."""
    t = token.lower()
    for a, b in _DIGRAPHS:
        t = t.replace(a, b)
    out = []
    for i, ch in enumerate(t):
        if ch in _AZ_DIGIT:
            out.append(_AZ_DIGIT[ch])
        elif ch in "aeiou":
            out.append("")
        elif ch == "y":
            out.append("y" if i == 0 else "")
        elif ch.isascii() and ch.isalpha():
            out.append(ch)
    return re.sub(r"(.)\1+", r"\1", "".join(out))


def lossy(sk: str) -> str:
    return re.sub(r"(.)\1+", r"\1", sk.translate(_LOSSY))


def deleet_token(tok: str) -> str:
    if any(c.isalpha() for c in tok) and any(c in LEET_FOLD for c in tok) and "@" not in tok[1:-1]:
        return "".join(LEET_FOLD.get(c, c) for c in tok)
    if tok and all(c in LEET_FOLD or c.isalpha() for c in tok) and sum(c in LEET_FOLD for c in tok) >= 2:
        return "".join(LEET_FOLD.get(c, c) for c in tok)
    return tok


def despace(text: str) -> str:
    """Join runs of >=3 single characters separated by single spaces."""
    out_lines = []
    for line in text.split("\n"):
        chunks = re.split(r"[ \t]{2,}", line)
        new_chunks = []
        for chunk in chunks:
            toks = chunk.split(" ")
            buf: list[str] = []
            res: list[str] = []
            for t in toks + [""]:
                if len(t) == 1 and not t.isspace():
                    buf.append(t)
                    continue
                if len(buf) >= 3:
                    res.append("".join(buf))
                else:
                    res.extend(buf)
                buf = []
                if t:
                    res.append(t)
            new_chunks.append(" ".join(res))
        out_lines.append("  ".join(new_chunks))
    return "\n".join(out_lines)


def decode_b64_candidates(text: str) -> list[str]:
    """Decode Base64-looking runs that turn into readable UTF-8 text."""
    found = []
    for m in _B64_RE.finditer(text):
        blob = m.group(0).replace("-", "+").replace("_", "/")
        blob += "=" * (-len(blob) % 4)
        try:
            raw = base64.b64decode(blob, validate=True)
            dec = raw.decode("utf-8")
        except (binascii.Error, ValueError, UnicodeDecodeError):
            continue
        if len(dec) < 8:
            continue
        ok = sum(1 for ch in dec if ch.isalnum() or ch.isspace() or ch in ".,;:!?'\"@/-_()[]،؟")
        if ok / len(dec) >= 0.9 and any(ch.isspace() for ch in dec):
            found.append(dec)
    return found


# -------------------------------------------------------------- tokenising
def _is_address(tok: str) -> bool:
    if re.search(r"\w@\w", tok):
        return True
    return tok.startswith(("http://", "https://", "www."))


def tokenize(folded: str, blob_min: int = 0, source_tokens: list[str] | None = None) -> list[Tok]:
    toks: list[Tok] = []
    sent = 0
    for line in folded.split("\n"):
        for raw in line.split():
            ends = raw[-1] in _SENT_END
            core = raw.strip(_STRIP_CHARS)
            if core and core not in _DETACHED_ARTICLES:
                addr = _is_address(core)
                text = core.replace("'", "")
                latin = any("a" <= c <= "z" for c in core)
                sk = skeleton(core) if latin and not addr else ""
                toks.append(Tok(text=text, sent=sent, sk=sk, sk_lossy=lossy(sk) if sk else "",
                                az_digit=any(c in _ARABIZI_DIGITS for c in core) and latin,
                                address=addr,
                                blob=bool(blob_min) and len(text) >= blob_min))
            if ends:
                sent += 1
        sent += 1
    return toks


def views(text: str, depth: int = 0) -> list[View]:
    """All normalised views of a text (recursing once into decoded Base64)."""
    nfkc = unicodedata.normalize("NFKC", text)
    clean, smuggled = strip_invisible(nfkc)
    folded = fold(clean)
    prefix = "" if depth == 0 else f"b64:{depth}/"
    out = [View(prefix + "base", tokenize(folded))]

    joined = despace(folded)
    if joined != folded:
        out.append(View(prefix + "despaced", tokenize(joined, blob_min=15)))

    base_tokens = out[0].tokens
    if any(deleet_token(t.text) != t.text for t in base_tokens):
        deleeted = []
        for t in base_tokens:
            d = deleet_token(t.text)
            if d == t.text:
                deleeted.append(t)
            else:
                sk = skeleton(d) if not t.address else ""
                deleeted.append(Tok(text=d, sent=t.sent, sk=sk, sk_lossy=lossy(sk) if sk else "",
                                    az_digit=True, address=t.address, blob=t.blob))
        out.append(View(prefix + "deleet", deleeted, lossy=True))

    if re.search(r"[a-z]", folded):
        out.append(View(prefix + "rot13", tokenize(codecs.encode(folded, "rot_13"))))

    if smuggled.strip():
        out.append(View(prefix + "tags", tokenize(fold(smuggled))))

    if depth < 2:
        for dec in decode_b64_candidates(clean):
            out.extend(views(dec, depth + 1))
    return out
