# Changelog

## 1.5.0.16

- Fixed: 1.5.0.15 could lose or hide the Activity log button in the top bar after changing the bar layout.
- The charge limit is put back once after each restart, never fought over: if you change it somewhere else,
  Ally Hub leaves it alone until the next restart. Importing a setup file keeps its limit too.
- Decky store cards no longer show "Turn off" (that's under Store → Installed now), and Installed says
  "Nothing installed yet." when it's empty.

## 1.5.0.15

- **Touch scrolling, fixed from your report.** Your drags were arriving fine but a check meant for sideways swipes
  blocked every one. Drags now scroll as soon as your finger moves up or down.
- **The battery charge limit no longer needs a password.** "Allow all" in Checkup covers it too (one password,
  once); after that, changing the limit is instant, and Ally Hub keeps your limit after every restart.
- **Store, one place per thing:** the Installed section is the only place to turn off or remove anything, Decky
  plugins included, and it only shows in Advanced. Store cards install and update. The extra Launchers card and the
  Decky store's own "Installed" filter are gone (Store → Launchers and Installed cover them).
- The Activity log button in General shows only in Simple, where the Activity log section is hidden.

(Numbered 1.5.0.15 so it's newer than every earlier test build.)

## 1.5.0.8

- **Touch scrolling, second try.** Dragging now works whether Game Mode sends your finger as a touch or as a mouse,
  and quick repeated flicks scroll too. The first few drags are written to the activity log (what kind of input
  arrived and how far it moved), so if it still doesn't scroll, the next report shows why.
- **Home is simpler.** The "Finish setting up" and "Set a password" notices are gone: Checkup right below lists
  those, with their fix. Checkup's separate Lighting and Game Boost permission rows are folded into "Password
  prompts", and Restart Decky lives only in Checkup.

## 1.5.0.7

- **The password prompt is part of Ally Hub now**: a dark panel near the top of the screen, so the Steam keyboard
  never covers it, and the keyboard opens by itself. Every typing box in Ally Hub sits up top the same way.
- Fixed: "Password prompts" in Checkup never cleared after Allow all. Tap Allow all one more time; from then on
  it stays cleared.
- Fixed: Checkup said "Charge limit: stops at 0%" when no limit was set.

## 1.5.0.6

- **Scroll with your finger like a phone.** Drag any page or list on the touch screen and it follows your finger,
  then glides when you let go. A tap still presses buttons, and sliders, text boxes and dropdowns work as before.
- **Wider scroll bar** on the right, easier to grab with a thumb.

## 1.5.0.5

- Fixed: "Allow all" in Checkup no longer reports "Lighting permission didn't take" while HueSync is in
  charge of the lights. Lighting is skipped then, so there was nothing to check.

## 1.5.0.4

- Fixed: "Couldn't reach GitHub" when checking for updates with an error-report access key that isn't allowed to
  read the repo. Updates are read without the key in that case (the repo is public). The message now also says
  why GitHub didn't answer.

## 1.5.0.3

- **One password for everything.** Checkup has a "Password prompts" check: one tap and one password set up
  lighting, Game Boost and Quick Access panel updates together, so they stop asking.
- **The Quick Access panel updates itself.** After that one password, panel updates need no password: Ally Hub
  updates the panel by itself when it updates (never during a game), and "Update the panel" works right away.

## 1.5.0.2

From the latest error reports:
- Fixed: an update could be rolled back when the handheld restarted right after it (the 144 Hz test's restart
  looked like a crash). Being closed or restarted is never counted as a crash now.
- Fixed: reports arrived without their logs, because the access key can't add comments. The logs now go into the
  report itself; a repeat of a known problem opens a new report instead of failing; and a report that keeps failing
  stops retrying after a while instead of trying every minute forever.
- Fixed: an installer that complains even though the app installed fine (Decky on an Ally Z1E) no longer shows
  "didn't finish". Ally Hub checks whether the app is there.
- 144 Hz test: one or two skipped frames in a 30 second run counts as smooth, and the summary names the screen
  setting where touch stopped instead of saying "every method".

## 1.5.0.1

- **After a 144 Hz or test restart, Ally Hub opens the way the Play button does**, so it shouldn't get stuck at
  Steam's "Launching" anymore. The countdown starts when Ally Hub's window is actually up. If it still gets stuck,
  that's reported automatically with Steam's own launch log.
- **Y opens the Steam keyboard.** Menu now refreshes.
- Fixed: on a handheld where Decky Loader's files were left behind but its service was gone, Checkup offered
  "Restart Decky", which failed. It now says what's wrong and offers Repair, which reinstalls Decky and keeps
  your plugins.
- Task output no longer fills with "wrong ELF class" lines from Steam's overlay, so real errors are easy to read.

## 1.5.0

**Controls and look**
- The left stick scrolls the page and the right stick moves a pointer. A or R3 clicks where it points; press the
  D-pad and A goes back to the highlighted control.
- Highlighted buttons no longer cut off their text, and button text stays readable with any accent color.
- Pop-up panels open with a button already selected for the controller.

**Ring lighting**
- True colors on the rings: presets no longer look washed out toward white.
- Much smoother effects: a one-color frame is a single message to the lighting chip, so breathe, cycle, wave and
  pulse run at full speed. On battery, Smooth stays at 15 frames a second and Silky at 20.
- The brightness slider follows how your eyes see the lights, so low settings get much dimmer, the rainbow spiral
  included.
- Lighting stops asking for your password: the permission is remembered across restarts and sleep. Run the
  lighting permission once more (Checkup → Fix or Test lights) to set it up.
- Neon Vortex works again.

**Experimental (Advanced only, Games → Performance)**
- 144 Hz in Game Mode: one switch lets the screen go from 48 up to 144 Hz. The handheld restarts, Ally Hub opens
  with a countdown once Steam is ready, and if you don't keep it, it goes back to 120 Hz by itself, even on a black
  screen. You may see skipped frames with VRR on.
- 144 Hz test: a guided check, one question per screen, that tries several ways of driving the screen at 144 Hz
  and checks the picture, touch and frames after each restart. It explains what it found and sends the results as
  a report.
- Frame meter: measured Hz, frame time, jitter and skipped frames with a live graph.

**Security**
- Phone remote: PIN guesses are capped across all devices and connections, and malformed requests can't use up
  memory.
- Shared profiles can't turn on SSH, move save backups or carry broken colors, and the import screen lists every
  app it would install.
- Settings backups are private and never include the phone remote's PIN.
- Downloads are https only, and Decky store plugins without a store checksum aren't installed.
- The password prompt names the task asking for it.
- Error reports need a fine-grained access key, and report issues are locked after upload.

**Fixes**
- Small fixes and tidy-ups.

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
