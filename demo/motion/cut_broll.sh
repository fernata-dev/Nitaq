#!/usr/bin/env bash
# Cut clean B-roll clips (window content only: no captions, no title bar) from the real demo video.
# usage: bash demo/motion/cut_broll.sh        -> demo/motion/broll/*.mp4 (1618x838, 30 fps, git-ignored)
# Timecodes = scene starts in demo/Nitaq_Full_Demo.mp4 (tools/video/scenes.json order) + 0.4 s, avoiding fades.
set -euo pipefail
cd "$(dirname "$0")"
SRC=../Nitaq_Full_Demo.mp4
mkdir -p broll
cut() {  # name start duration
  ffmpeg -y -loglevel error -ss "$2" -i "$SRC" -t "$3" -vf "crop=1618:838:151:67" \
    -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -an "broll/$1.mp4"
  echo "broll/$1.mp4  ($3 s)"
}
cut b01_tests_pass        10.8  13.1   # python -m pytest -> 261 passed (output x2 speed)
cut b02_scan_clean        28.2   9.3   # nitaq scan benign_skill.md -> exit code 0
cut b03_scan_poisoned     38.3  15.0   # nitaq scan malicious_skill.md -> high=14, exit code 3
cut b04_five_forms        57.5  21.2   # same_attack.py: five forms, D2 4/5, nitaq hook DENY 5/5
cut b05_simulation        83.2  21.5   # nitaq bench eval: D0 100% D1 100% D2 94.1% D5 33.3% (output x3)
cut b06_app_home         108.9   6.5   # app home + example buttons
cut b07_app_email        116.3  15.3   # suspicious e-mail -> 6 hidden parts
cut b08_app_word_xray    132.4  12.0   # Word file, white text, X-ray "hidden" view
cut b09_app_invisible    145.3  10.0   # invisible Unicode characters decoded
cut b10_app_protect      157.6  20.6   # device protection: status -> protect preview diff
