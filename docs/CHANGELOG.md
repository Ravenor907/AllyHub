# Changelog

## 1.3.4

- **RGB Spiral and Neon Vortex now use the lighting chip's built-in spiral by default.** It's smooth and uses no
  battery; Ally Hub's own spiral looked choppy. Your saved spirals switch over once. Ally Hub's style is still under
  Style if you want your own colors (the chip's spiral is rainbow only).

## 1.3.3

- **Setup no longer sends you to change your password over and over.** Ally Hub now checks again after the
  password window closes and before every install, so once a password is set it stops asking.
- **New "I already have one" button** on the password step and in the password prompt, for when Ally Hub can't
  tell that a password is already set. It's remembered.
- Closing Ally Hub no longer closes the password window halfway through.

## 1.3.2

- **First launch walks you through setup** (Home → Setup): sudo password, Game Mode library and background helper,
  essentials you pick (Decky Loader, Ally Hub in Quick Access, Ludusavi), lighting and a few favorites. Skip any
  step; Home shows a **Finish setting up** card with whatever is left, and Setup can be run again any time.
- **The installer does more on a brand new install:** it adds Ally Hub to your Game Mode library and turns the
  background helper on. Updates and reinstalls leave your settings alone.
- **Save time machine (Tools → Saves):** a snapshot of a game's saves every time it starts, keeping the last few per
  game. Restore any of them from Game Mode; your saves as they are now are kept first, and **Undo the last restore**
  puts them back. Uses Ludusavi (one tap to install).
- **Sleep guardian (Tools → Sleep):** every sleep is tracked: how long, how much battery it used, what woke the
  handheld, and sleeps that failed. It flags heavy drain and devices that keep waking it, and can stop a USB device
  from waking it (the power button always works).

## 1.2.3

- **Desktop Mode is no longer blown up.** The automatic interface size now takes the desktop's own display scaling
  into account instead of adding to it, so Ally Hub looks the same size in Desktop Mode and Game Mode.

## 1.2.2

- **Quick Access panel:** Ally Hub in the ••• menu while you play. Battery and temperatures, switches for the game
  you're playing, Game Boost, lighting and a save backup button. Add it under Tools → Games (needs Decky Loader).
- **Game settings (Tools → Games):** switches instead of typing launch options: FSR 4, frame generation, Steam Deck
  mode, an older-game fix and a troubleshooting log. Pick the Proton per game, and get help when a game won't start
  (try another Proton, reset its Windows files with a backup, send the log, check its files).
- **Storage saver (Tools → Storage):** each game's real size including its shader cache and Windows files, and a
  one-tap cleanup of what Steam leaves behind. Anything that can hold saves starts unticked.
- **Never stuck with a bad plugin:** every Decky plugin can be turned off and back on without uninstalling it, from
  its card or the new **Your plugins** list on the Plugin store page. **Turn all plugins off** finds a troublemaker
  fast, and **Turn them back on** restores exactly those.
- **Launchers:** **Hide from Steam** keeps a launcher installed but takes its tile out of your library. Adding it
  back just restores the tile.
- **EmuDeck** now has a Remove button (EmuDeck's own uninstaller, or just its app if it was never set up).
- **Interface and text size are remembered separately for Game Mode and Desktop Mode**, so switching no longer
  means changing the size every time.

## 1.1.1

- **Update channel:** Settings → Updates can now follow **Testing** builds to get new features before everyone
  else. Everyone stays on **Stable** unless they switch, and switching back offers the stable version right away.

## 1.1.0

- **Library art:** blank blue tiles for launchers and Ally Hub itself now get a cover, banner, hero and icon,
  made on your handheld from each program's own icon. No SteamGridDB, nothing downloaded. New launchers get theirs
  automatically, and Install → Launchers has **Fix artwork** and **Use my own picture**.
- Pictures you set yourself are never replaced.

## 1.0.0

The first release of Ally Hub for the ROG Xbox Ally X on SteamOS.

- **Made for Game Mode:** five console-style tabs, full controller navigation, and pop-ups that open inside the app.
- **Mods & plugins:** Decky Loader, Ally Center, SimpleDeckyTDP, Lossless Scaling and OptiScaler frame gen, EmuDeck and the Decky Plugin Store.
- **Apps:** 30 curated apps from Flathub, each with install, update and remove.
- **Launchers:** Battle.net, Epic, EA, Ubisoft, GOG and more, added to your Steam library, with uninstall and a leftover cleaner.
- **Performance:** Game Boost while you play, a one-tap system tune-up, and FSR 4 for every game. All undoable.
- **Lighting:** animated ring effects, a customizable RGB Spiral, battery and per-game colors, or HueSync.
- **Themes:** 8 themes, accent colors, interface size, and tabs on the top or as icons down the sides.
- **Health & Doctor:** temps, power draw, battery history, drain per game and one-tap fixes.
- **Background agent:** dock mode, Update Guardian, health logging and scheduled save backups.
- **Phone remote:** a PIN-protected page for battery, temps, lighting and Wake-on-LAN.
- **Updates & reports:** updates itself and rolls back a bad version on its own. Report a problem sends logs and a system snapshot in one tap.
