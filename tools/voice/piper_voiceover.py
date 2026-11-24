"""Make the film narration on this computer with Piper (local neural text-to-speech, no account, no internet).

    python tools/voice/piper_voiceover.py ar        # demo/voiceover/AR.md -> demo/voiceover/audio/piper/vo_ar_01.wav …
    python tools/voice/piper_voiceover.py en

Reads the same scene blocks as ElevenLabs (Part 2 of AR.md / EN.md). `[short pause]` and `[long pause]` become
silence; every other [bracket] direction is dropped (Piper does not take delivery tags).
Setup (once): python3 -m venv ~/.local/share/nitaq-voice/venv && ~/.local/share/nitaq-voice/venv/bin/pip install piper-tts
and put the voices in ~/.local/share/nitaq-voice/voices (ar_JO-kareem-medium, en_US-ryan-medium from rhasspy/piper-voices).
Run this file with that venv's python.
"""
from __future__ import annotations

import re
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VOICES = Path.home() / ".local" / "share" / "nitaq-voice" / "voices"
VOICE = {"ar": "ar_JO-kareem-medium", "en": "en_US-ryan-medium"}
PAUSE = {"short pause": 0.45, "long pause": 1.0}
SPEED = {"ar": 0.80, "en": 1.05}                     # length_scale: < 1 faster (the Arabic voice is slow by nature)


def scenes(lang: str) -> list[tuple[str, str]]:
    md = (ROOT / "demo" / "voiceover" / f"{lang.upper()}.md").read_text(encoding="utf-8")
    part2 = md[md.index("\n## ", md.index("```text")):]          # scene-by-scene part, after the full text
    out = []
    for m in re.finditer(r"`(vo_%s_\d\d)\.mp3`\s*\n```text\n(.*?)\n```" % lang, part2, re.S):
        out.append((m.group(1), m.group(2).strip()))
    return out


def pieces(text: str) -> list[tuple[str, float]]:
    """Split on pause tags: [(text, silence_after_seconds)], other tags removed."""
    out, buf = [], ""
    for tok in re.split(r"(\[[^\]]+\])", text):
        if tok.startswith("["):
            tag = tok[1:-1].strip().lower()
            if tag in PAUSE:
                out.append((buf, PAUSE[tag]))
                buf = ""
            continue
        buf += tok
    out.append((buf, 0.6))
    clean = []
    for t, pause in out:
        t = re.sub(r"\s+", " ", t.replace("…", "، " if re.search(r"[؀-ۿ]", t) else ", ").replace("—", ", ")).strip(" ,،")
        if t:
            clean.append((t, pause))
        elif clean:
            clean[-1] = (clean[-1][0], clean[-1][1] + pause)
    return clean


def main(lang: str) -> int:
    from piper import PiperVoice
    from piper.config import SynthesisConfig
    voice = PiperVoice.load(str(VOICES / f"{VOICE[lang]}.onnx"))
    cfg = SynthesisConfig(length_scale=SPEED[lang])
    out_dir = ROOT / "demo" / "voiceover" / "audio" / "piper"
    out_dir.mkdir(parents=True, exist_ok=True)
    rate = voice.config.sample_rate
    for name, text in scenes(lang):
        pcm = bytearray()
        for chunk_text, pause in pieces(text):
            for chunk in voice.synthesize(chunk_text, syn_config=cfg):
                pcm += chunk.audio_int16_bytes
            pcm += b"\x00\x00" * int(rate * pause)
        with wave.open(str(out_dir / f"{name}.wav"), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(pcm))
        print(f"{name}.wav  {len(pcm) / 2 / rate:5.1f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "ar"))
