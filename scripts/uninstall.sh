#!/usr/bin/env bash
# Removes Ally Hub itself. Mods, apps and your backups in ~/AllyHub-Backups are left alone.
set -u
for unit in allyhub-agent.service; do
    systemctl --user disable --now "$unit" 2>/dev/null
    rm -f "$HOME/.config/systemd/user/$unit"
done
systemctl --user daemon-reload 2>/dev/null
rm -rf "$HOME/.local/share/allyhub" "$HOME/.config/allyhub"
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
if [ -n "$RULES" ]; then
    echo "Removing Ally Hub's system settings (lighting, charge limit, performance; needs your password)"
    if [ -f /etc/systemd/system/allyhub-zram.service ]; then
        sudo systemctl disable --now allyhub-zram.service 2>/dev/null
    fi
    sudo rm -f $RULES
    sudo rmdir /etc/allyhub 2>/dev/null
    sudo systemctl daemon-reload 2>/dev/null
    echo "Restart once to return every performance setting to SteamOS's defaults."
fi
echo "Ally Hub removed. Your backups are still in ~/AllyHub-Backups."
