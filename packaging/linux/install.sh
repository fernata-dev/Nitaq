#!/bin/sh
# Add the Nitaq app to your Linux app menu (only touches two files in your home folder).
set -e
here="$(cd "$(dirname "$0")" && pwd)"
apps="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/512x512/apps"
mkdir -p "$apps" "$icons" "$HOME/.local/bin"
cp "$here/nitaq-app" "$HOME/.local/bin/nitaq-app"
chmod +x "$HOME/.local/bin/nitaq-app"
cp "$here/nitaq.png" "$icons/nitaq.png"
cat > "$apps/nitaq-app.desktop" <<DESK
[Desktop Entry]
Type=Application
Name=Nitaq
Name[ar]=نِطاق
Comment=Stops AI agents from acting on hidden instructions
Comment[ar]=بيمنع وكلاء الذكاء الاصطناعي من تنفيذ الأوامر المدسوسة
Exec=$HOME/.local/bin/nitaq-app
Icon=nitaq
Terminal=false
Categories=Utility;Security;
DESK
echo "Nitaq added to your app menu. Run it from there, or: ~/.local/bin/nitaq-app"
