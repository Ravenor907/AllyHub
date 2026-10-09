# Changelog

## 1.3.7.10

- **Every part of the Store works with the controller:** Essentials, Mods, Apps, Decky plugins, Installed and Launchers
  are now the Store's sections, picked with LT/RT. The extra row of chips you couldn't reach is gone.
- **Quick fixes are gone, not lost:** each fix moved to where you'd look for it. Restart Decky is under Your plugins,
  Update all apps is under Apps, cleanups are in Storage, and the Checkup now checks that Ally Hub is in your Game
  Mode library.
- **All cleanup is in one place:** Home > Storage > More cleanup clears the shader cache, unused app runtimes and
  leftovers from removed launchers.
- **One Saves card:** snapshots when a game starts and backups on a schedule share the Save time machine card.
- **Settings is shorter:** Backups moved into General, the full changelog became a "What's new" button, and alerts
  show once, in the Checkup, instead of twice on Home.

## 1.3.7.9

- **One place for each job:** installed Decky plugins are turned off or removed only under Your plugins. Store
  cards now just install, or show Update when there's a newer version. HueSync and Controller glyphs no longer
  repeat install or remove buttons once their plugin is in, and Quick fixes no longer repeats the Checkup's Decky
  repair.
- **Controller glyphs has step-by-step instructions**, including how to change the icons or switch them off later.
- **Clearer names:** "Activity log" everywhere (was also "View log"), "Decky plugins", "Remove unused app runtimes",
  "Back up on a schedule" and "Settings backup".

## 1.3.7.8

- **Calmer pages:** the 22 wordiest card and page descriptions are now one short line each, so every screen
  reads at a glance. Nothing moved and no features changed.

## 1.3.7.7

- **Controller glyphs card (Customize > Theme):** installs CSS Loader from the plugin store (and Decky first if
  needed), then shows the two steps for the Handheld Controller Glyphs theme and a check once it's installed.
  Remove CSS Loader is one tap.

## 1.3.7.6

- Removed the Xbox Ally X controller layout card that 1.3.7.5 added. It's not coming back.

## 1.3.7.4

- **Failures now say what happened and what to do**, in plain words: a cancelled password, no internet, no space
  left. No more "exit code 1" with a wall of log.
- **Each task says when it's done** (with how long it took), and the status shows how many are still waiting.
- An unexpected error no longer looks like a crash: Ally Hub says it's still running and whether a fix can follow.

## 1.3.7.3

- **Calmer, smoother Ally Hub spiral:** it spins about half as fast, and the colors blend from frame to frame
  instead of jumping between the rings' four zones.
- **Quick Access panel:** a speed slider for animated effects, switches for battery rings, low battery flash and
  the save time machine. Update the panel from Games → Game settings.

## 1.3.7.2

- The info line at the bottom of Home is no longer cut off, and it shows a short device name ("ROG Xbox Ally X")
  instead of the vendor and model codes.
- **Smoother Ally Hub lighting:** frames are now timed so the time spent sending each one counts toward the frame
  rate, and on battery it runs at up to 15 frames a second instead of 10.
- **A better-looking Quick Access panel:** a battery card with a level bar and CPU, GPU and power at a glance, and a
  "Now playing" header for the game's switches. Update it from Games → Game settings.

## 1.3.7.1

First test build under the new numbering: Stable 1.3.7 plus test revision 1 (at most 10 before Stable). On top of
1.3.7 it has, all still being tested:
- The new layout (1.4.0, still being fixed: it didn't open on a real Ally).
- RGB Spiral and Neon Vortex on the chip's own spiral by default.
- Ally Hub Testing Rescue and the test-build warnings.

## 1.3.7

- Ally Hub now understands test build numbers like 1.3.7.1, so the Testing channel can deliver test builds again.
  Nothing else changes on Stable.

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
