#!/usr/bin/env bash
# Ally Hub installer for SteamOS (run in Desktop Mode, no sudo needed)
set -euo pipefail

APP_DIR="$HOME/.local/share/allyhub"
BIN_DIR="$HOME/.local/bin"
DESKTOP_FILE="$HOME/.local/share/applications/allyhub.desktop"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The repo keeps files in folders (app/, scripts/, docs/); the install itself is flat
ROOT="$SRC"
[ -d "$SRC/../app" ] && ROOT="$(cd "$SRC/.." && pwd)"

echo "==> Installing Ally Hub to $APP_DIR"
mkdir -p "$APP_DIR" "$BIN_DIR" "$(dirname "$DESKTOP_FILE")"
for f in allyhub.py core.py agent.py gui.py allyhub.svg VERSION CHANGELOG.md README.md install.sh uninstall.sh; do
    for d in "$ROOT/app" "$ROOT/scripts" "$ROOT/docs" "$ROOT"; do
        if [ -f "$d/$f" ]; then
            [ "$d/$f" -ef "$APP_DIR/$f" ] || cp "$d/$f" "$APP_DIR/$f"
            break
        fi
    done
done
rm -rf "$APP_DIR/__pycache__"

# Private Python environment so we never touch the read-only system
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
    echo "==> Creating Python environment"
    if ! python3 -m venv "$APP_DIR/venv" 2>/dev/null; then
        echo "    ensurepip missing, bootstrapping pip"
        rm -rf "$APP_DIR/venv"
        python3 -m venv --without-pip "$APP_DIR/venv"
        curl -sSL https://bootstrap.pypa.io/get-pip.py -o "$APP_DIR/get-pip.py"
        "$APP_DIR/venv/bin/python" "$APP_DIR/get-pip.py" -q
        rm -f "$APP_DIR/get-pip.py"
    fi
fi

echo "==> Installing PySide6 (Qt), this can take a minute"
"$APP_DIR/venv/bin/python" -m pip install -q --upgrade pip
"$APP_DIR/venv/bin/python" -m pip install -q --upgrade PySide6-Essentials

cat > "$BIN_DIR/allyhub" <<EOF
#!/bin/sh
exec "$APP_DIR/venv/bin/python" "$APP_DIR/allyhub.py" "\$@"
EOF
chmod +x "$BIN_DIR/allyhub"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Ally Hub
Comment=Mods, plugins, themes, lighting and automation for the ROG Xbox Ally X
Exec=$BIN_DIR/allyhub
Icon=$APP_DIR/allyhub.svg
Terminal=false
Categories=Utility;Settings;Game;
EOF
chmod +x "$DESKTOP_FILE"

# Handy desktop shortcut
if [ -d "$HOME/Desktop" ]; then
    cp "$DESKTOP_FILE" "$HOME/Desktop/allyhub.desktop"
    chmod +x "$HOME/Desktop/allyhub.desktop"
fi

command -v update-desktop-database >/dev/null 2>&1 && \
    update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true

# Brand new install: turn the background helper on and add Ally Hub to Game Mode (does nothing on updates)
FRESH=0
[ -f "$HOME/.config/allyhub/config.json" ] || FRESH=1
"$APP_DIR/venv/bin/python" "$APP_DIR/allyhub.py" --first-install || true

# Updating: restart the agent on the new code
if [ "$FRESH" = 0 ] && [ -f "$HOME/.config/systemd/user/allyhub-agent.service" ]; then
    systemctl --user daemon-reload
    systemctl --user restart allyhub-agent.service 2>/dev/null && echo "==> Agent restarted"
fi

echo
echo "Done! Open \"Ally Hub\" from the app menu, your desktop, or your Game Mode library."
echo "It walks you through the rest on first launch."
