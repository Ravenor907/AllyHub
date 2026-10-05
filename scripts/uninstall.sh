#!/usr/bin/env bash
# Removes Ally Hub itself. Mods, apps and your backups in ~/AllyHub-Backups are left alone.
set -u
for unit in allyhub-agent.service; do
    systemctl --user disable --now "$unit" 2>/dev/null
    rm -f "$HOME/.config/systemd/user/$unit"
done
systemctl --user daemon-reload 2>/dev/null
# The Game Mode library tile (through Steam itself, while Steam and Decky are running)
APP_DIR="$HOME/.local/share/allyhub"
TILE=0
if [ -f "$APP_DIR/core.py" ] && command -v python3 >/dev/null; then
    python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import core; sys.exit(0 if core.cef_remove_shortcuts(["Ally Hub"]) else 1)' \
        "$APP_DIR" 2>/dev/null && TILE=1
fi
rm -rf "$APP_DIR" "$HOME/.config/allyhub" "$HOME/.local/share/allyhub-rescue"
rm -f "$HOME/.local/share/applications/allyhub-testing-rescue.desktop" "$HOME/Desktop/allyhub-testing-rescue.desktop"
rm -f "$HOME/.config/environment.d/90-allyhub-games.conf"
rm -f "$HOME/.local/bin/allyhub" \
      "$HOME/.local/share/applications/allyhub.desktop" \
      "$HOME/.local/share/applications/allyhub-gamemode.desktop" \
      "$HOME/Desktop/allyhub.desktop"
RULES=""
for r in /etc/udev/rules.d/99-allyhub-leds.rules /etc/udev/rules.d/99-allyhub-charge.rules /etc/udev/rules.d/70-allyhub-hid.rules \
         /etc/udev/rules.d/71-allyhub-nowake.rules \
         /etc/udev/rules.d/70-allyhub-ntsync.rules /etc/tmpfiles.d/allyhub-boost.conf /etc/tmpfiles.d/allyhub-tuneup.conf \
         /etc/sysctl.d/99-zz-allyhub.conf /etc/sysctl.d/99-zz-allyhub-zram.conf /etc/modules-load.d/allyhub-ntsync.conf \
         /etc/systemd/system/allyhub-zram.service /etc/allyhub/zram.sh; do
    [ -f "$r" ] && RULES="$RULES $r"
done
QAM="$HOME/homebrew/plugins/AllyHub"          # Ally Hub's Quick Access panel (a Decky plugin, owned by root)
if [ -n "$RULES" ] || [ -d "$QAM" ]; then
    echo "Removing Ally Hub's system settings and Quick Access panel (needs your password)"
    if [ -f /etc/systemd/system/allyhub-zram.service ]; then
        sudo systemctl disable --now allyhub-zram.service 2>/dev/null
    fi
    [ -n "$RULES" ] && sudo rm -f $RULES
    sudo rmdir /etc/allyhub 2>/dev/null
    sudo systemctl daemon-reload 2>/dev/null
    if [ -d "$QAM" ]; then
        sudo rm -rf "$QAM" && sudo systemctl restart plugin_loader 2>/dev/null
    fi
    [ -n "$RULES" ] && echo "Restart once to return every performance setting to SteamOS's defaults."
fi
[ "$TILE" = 1 ] || echo "If Ally Hub is still in your Game Mode library, remove it there: Manage > Remove non-Steam game."
echo "Ally Hub removed. Your backups are still in ~/AllyHub-Backups."
