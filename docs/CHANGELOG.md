# Changelog

## 1.4.3

- **Ally Hub shows up once in the app menu**, under Utilities, instead of under Games, Utilities and System. Existing
  installs are fixed automatically.

## 1.4.2

- **Ally Hub Testing Rescue:** on the Testing channel there's now an entry in the app menu (and on the desktop,
  next to Ally Hub) that can roll back the test build, go back to Stable or uninstall, even when Ally Hub won't open.
  It goes away when you switch back to Stable.
- **Clear warning before switching to Testing**, and a reminder on Settings → General while you're on it: test
  builds can break, here's the way out, and if all else fails, uninstall and reinstall.
- From now on only the developer decides when something goes to Stable.

## 1.4.1

- **Automatic rollback now covers the app window, not just the background helper.** Each part has to prove itself
  after an update. If Ally Hub's window fails to start 3 times (or crashes in its first two minutes), the update rolls
  back on its own and the helper restarts on the old version. Before, a working helper ended the check early, which
  is why 1.4.0 didn't roll back for you.
- Opening Ally Hub again while it's already open, or closing it quickly, no longer counts as a failed start.

## 1.4.0

A new, simpler layout: everything is where you'd look for it, and the expert controls stay out of the way until you
want them.
- **Five tabs, fewer sections:** Home (Overview, Battery & sleep, Storage), Store (Browse, Launchers), Games (Game
  settings, Performance, Saves), Customize (Lighting, Theme) and Settings (General, Connections, Backups, Activity).
  20 sections became 15 (13 in Simple once setup is done).
- **Home at a glance:** the Overview now has a Checkup that only shows what needs you, with the fix, plus Quick fixes.
  Ally Doctor and Tweaks moved in here.
- **One store:** Mods, Apps and Decky plugins are in Store → Browse, with Essentials and Installed views. One list of
  essentials, the same one setup offers.
- **Simple / Advanced** (Settings → General). Simple is the default and tucks away the system tune-up, Proton per game,
  wake blockers, SSH and the activity log. Advanced shows everything.
- **Things that lived in two places now live in one:** battery care sits with sleep, SD card and shader cache tools
  with Storage, scheduled save backups with Saves, battery/per-game/dock lighting with Lighting, the boot video with
  Theme, SSH with Connections.
- **Back up settings no longer asks for your password.**
- Pages like Saves, Sleep, Storage, Game settings and Setup no longer open blank.
- The "agent" is now called the **background helper** everywhere, and any feature that needs it simply turns it on.
- Importing a profile is a list you can pick from with the controller.
- With the tabs on the sides, messages like "Saved" now pop up instead of disappearing.

## 1.3.5

Safety and privacy fixes from a security review:
- **Shared profiles are checked before anything runs.** A tampered profile can no longer slip commands into the
  charge limit or app names, and profiles no longer carry (or change) your phone remote PIN or your PC's network
  address.
- **Phone remote:** five wrong PINs and that device has to wait 5 minutes. The PIN no longer shows up in the
  browser's address bar or history, you stay signed in with a random session instead of the PIN, and the remote only
  answers to the handheld's own address.
- **Downloads:** installers only run after they finished downloading (a failed or cut-off download is never run),
  and Decky store plugins are checked against the store's checksum.
- **Error reports** no longer include your Steam account number or your device's name.
- **An expired access key no longer stops updates.**
- Ally Hub's logs and settings are now private to your user, and the access key is private from the moment it's
  saved.
- Uninstalling also removes the Quick Access panel and the Game Mode library tile.

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
