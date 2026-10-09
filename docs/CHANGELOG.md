# Changelog

## 1.4.1.4

- Back to the usual Ally Hub look: the original icon, header, default theme and README. If 1.4.1.3 switched your
  theme, it switches back once.

## 1.4.1.3

- **New look:** the Ally Hub logo in the header and on the setup welcome, the new app icon (app menu, Game Mode
  library tile and desktop shortcut), and a black and orange "Ally Hub" theme, now the default. If you never picked
  a theme, you're switched to it once; any theme you choose later stays.
- The README has the new banner and poster.

## 1.4.1.2

- **Much smoother effects:** your video showed the rings only changing about 3 times a second, because every frame
  was five separate messages to the lighting chip, and it's slow to take each one. A one-color frame (breathe,
  cycle, wave, pulse and the like) is now a single message, zones that didn't change aren't re-sent, and a frame
  that didn't change sends nothing. Spirals still send a message per ring zone.
- **Breathing stays lit, colors stay true:** the color fix now only corrects how colors mix, so fades and the
  lowest point of a breathe are back to their old brightness instead of dropping to black. The default lowest
  brightness is also higher (25%, ROG Pulse 20%). Your own saved effects keep their setting.
- **On battery, Smooth stays at 15 frames a second** (1.4.1.1 dropped it to 13); Silky runs at 20.
- The activity log now notes how many frames a second the rings really get, once a minute while an effect runs.

## 1.4.1.1

- **True colors on the rings:** colors are now converted for LEDs before they're sent, so presets no longer look
  washed out toward white. Pure red, green, blue and white are unchanged.
- **Smoothness works on battery:** "Slow down to save power" used to cap every effect at 15 frames a second, so
  Smooth and Silky looked the same unplugged. It now runs at two thirds of your choice (Silky 20, Smooth 13), or pick
  "Keep full speed".
- **Neon Vortex works again:** it runs in Ally Hub's style, because the chip's own spiral can only show rainbow.
  Saved copies are fixed automatically.
- **Pointer clicks:** R3 now left-clicks where the pointer is, like A, and clicks on buttons and lists use the
  same reliable path as the D-pad.

## 1.4.1

- **New controls:** the left stick scrolls the page, the right stick moves a pointer and R3 right-clicks. The
  D-pad still moves between controls. While you use the pointer, A clicks wherever it points; press the D-pad and
  A goes back to the highlighted control.

## 1.4.0

**A cleaner, simpler Ally Hub.** Everything you had is still here, in fewer places:
- **New layout, made for the controller:** Home, Store, Games, Customize and Settings. LB/RB switch tabs and LT/RT
  switch sections, and every section is reachable with the buttons. No more rows of chips you can't get to.
- **Simple by default:** expert controls (tune-up, Proton per game, wake blockers, SSH, the activity log) wait under
  Settings → General → Advanced.
- **Home shows what needs you:** a Checkup that lists only problems, each with its fix, plus battery, temps and
  history. Battery & sleep and Storage sit next to it, and every cleanup is in one Storage card.
- **One store:** Essentials, Mods, Apps, Decky plugins, Installed and Launchers. Installed plugins are turned off or
  removed in one place (Your plugins).
- **Games:** per-game settings with the Quick Access panel, Performance, and one Save time machine card for
  snapshots and scheduled backups.
- **Clearer feedback:** failures say what happened and what to do, each task says when it's done, and an unexpected
  error no longer looks like a crash.
- **Lighting:** RGB Spiral and Neon Vortex use the chip's own smooth spiral by default, and Ally Hub's own spiral is
  calmer and blends between frames.
- **Quick Access panel:** a nicer look, a lighting speed slider, and switches for battery rings, low battery flash
  and the save time machine. Update it from Games → Game settings.
- **Controller glyphs (Customize → Theme):** installs CSS Loader and walks you through the Handheld Controller
  Glyphs theme.
- **Shorter Settings:** backups live in General, and release notes open from a "What's new" button.

## 1.3.7

- Ally Hub now understands test build numbers like 1.3.7.1, so the Testing channel can deliver test builds again.
  Nothing else changes on Stable.

## 1.3.6

- **Automatic rollback now covers the app window, not just the background helper.** After an update, each part has
  to prove itself. If Ally Hub's window fails to start 3 times (or crashes in its first two minutes), the update rolls
  back on its own and the helper restarts on the old version.
- Opening Ally Hub again while it's already open, or closing it quickly, no longer counts as a failed start.
- **Ally Hub shows up once in the app menu**, under Utilities, instead of under Games, Utilities and System. Existing
  installs are fixed automatically.

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
