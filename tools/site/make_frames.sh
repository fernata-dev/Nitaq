#!/bin/sh
# Hero "surveillance" frames for the website: tight crops of real Nitaq screenshots (docs/media) printed as
# coarse halftone (ImageMagick). Re-run after the screenshots change:  sh tools/site/make_frames.sh
set -e
cd "$(dirname "$0")/../.."
out=site/assets/frames
mkdir -p "$out"
frame() {  # name source crop negate
  magick "$2" -crop "$3" +repage -resize 270x203^ -gravity center -extent 270x203 -colorspace gray $4 \
    -contrast-stretch 2%x8% -sigmoidal-contrast 4,50% -ordered-dither h6x6o -filter point -resize 200% \
    -depth 1 -strip -set comment "Nitaq site frame: $2 crop $3, halftone h6x6o" "$out/$1.png"
}
frame mail    docs/media/app/phone-3-xray-hidden-ar.png 960x720+100+400 ""
frame skill   docs/media/03-scan-skill.png              860x645+31+170  -negate
frame page    docs/media/08-mcp-proxy-taint.png         720x540+31+300  -negate
frame tool    docs/media/07-mcp-proxy-allowlist.png     720x540+31+150  -negate
frame agent   docs/media/09-claude-code-hook.png        520x390+31+110  -negate
frame gateway docs/media/gateway-dashboard.png          590x443+589+392 -negate
echo "wrote $out/*.png"
