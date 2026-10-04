# Ally Hub: notes for Claude

Ally Hub is the owner's all-in-one mod, theme and automation app for his **ASUS ROG Xbox Ally X running SteamOS**
(Desktop Mode GUI plus Game Mode with controller navigation). This file is the shared memory for the daily
maintenance runs. Read it fully before changing anything.

## Architecture

Repo layout: code in `app/`, `scripts/install.sh` + `scripts/uninstall.sh`, `docs/CHANGELOG.md` +
`docs/CONTRIBUTING.md`, `assets/`, `tests/`, this file in `.claude/`. Only README.md, LICENSE and VERSION
sit at the top (a test enforces it). The install on the device is flat (`~/.local/share/allyhub/`);
`core.repo_file` / `REPO_DIRS` and install.sh find files in either layout, so never rename the folders or
move VERSION without making sure installed copies can still update.

| File | Role | Rules |
|---|---|---|
| `app/allyhub.py` | Entry point: `--agent`, `--apply-rgb`, `--gamemode`, `--fullscreen` | Keep tiny |
| `app/core.py` | Everything without Qt: config, system info, LEDs, catalog, profiles, themes, GitHub updates and error reports | **Standard library only** |
| `app/agent.py` | Background systemd user service: lighting, dock mode, health log, Update Guardian, save backups, phone remote, report upload, daily auto-update | **Standard library only** |
| `app/gui.py` | PySide6 GUI. No sidebar: `Hub.TABS` defines 5 top tabs (LB/RB), each a `GroupPage` with section chips (LT/RT). Home is the health report (`HealthPage`, section "Health", plus notices for a missing password or Decky); no shortcut tiles (the owner's call). Navigate in code with `hub.go("Section name")` | Only `PySide6-Essentials` modules (QtCore, QtGui, QtWidgets, QtNetwork). No QtCharts, no extra pip packages |
| `scripts/install.sh` / `scripts/uninstall.sh` | User-level install into `~/.local/share/allyhub` with a venv | No sudo in install.sh |
| `tests/run_tests.py` | Full test suite, runs without Qt or hardware | Must pass before any push |

**Lighting has two controllers (the owner's call).** `config["lighting"]["controller"]` defaults to
`"huesync"`: the **HueSync** Decky plugin (honjow) drives the rings, the agent never touches them, and
lighting automation is hidden. Customize → Lighting is a `LightingSection` stack: `HueSyncPage` (with a
"Use Ally Hub lighting" button) or the `LightingPage` studio when `controller == "allyhub"` ("Use HueSync
instead" switches back). Never run both: they fight.

**HueSync's Xbox Ally X sequence (BSD-3-Clause, credited in core.py):** pick the hidraw interface by HID
usage 0xFF31/0x0080 (`ally_hid_nodes`, `hid_collections` parses report descriptors), turn off Windows
Dynamic Lighting on the 0x59/0x01 interface with `[0x06, 0x01]`, and send RGB enable
`[0x5A, 0xD1, 0x09, 0x01, 0x02]` before colors (`hid_packets`). HueSync writes sysfs packed zones as hex
text (`encoding == "hex"`). The guided test probes each sysfs encoding by readback and skips any the
kernel changes, so the owner is only asked about methods that can work. One permission job
(`led_permission_cmd(leds)`, key `rgb-perms`) writes both udev rules; the job also chmods the files right away.
Never skip the job because a rule file exists (a stale one causes a restart loop). If access still fails
afterwards, `lighting_access_details` goes into a "Lighting permission didn't take" report.

**What works on the owner's Ally X:** sysfs is capped (hex reads back 0/255), and the kernel LED driver
re-sends its capped (blue) value over chip packets. The guided test tries `TEST_HID_METHODS` (m6 m7 m8 m2 m3
from `HID_METHODS`) as "Method N of 5", pauses the agent during the test (`pause_agent`), needs red, green
and blue to pass, records "Left and right don't match" as `Mixed L=x R=y`, and saves the winner as
`config["lighting"]["hid_method"]` (default `m3` when unset). Report rows show `hid:mN`. **m6 passes and is
the owner's saved method**: kernel lights off ONCE + settle, set/apply only on the first send or a
mode/brightness change (HueSync's custom path, `_HID_SESSION`). m1, m4 and m5 fail; m2-m4 get red right,
then stick or mix zones. Chip modes only show a slow breathe, so commit-once methods **stream software
frames** (`hid_streams`): `zone_frames(effect, t)` gives four zone colors (left/right half of each stick,
`ZONE_POS`), `hid_zone_frame` sends bare 0xB3 zone commands (set/apply only on the first frame, so no
chip-memory writes per frame), up to `STREAM_FPS_MAX` 30 fps from the agent's Animator. This is the one
sanctioned per-frame HID path; chip-mode effects (non-streaming methods, or Spiral with
`engine == "chip"`) go once per change. The GUI never writes the chip while the agent runs (two writers
interleave packets and mix zones). Spiral keys: direction, layout (linked/mirror/same), engine
(smooth/chip), rainbow; only spiral effects carry them.

Lighting: effects are plain dicts (`type`, `colors`, `speed`, `param`) rendered by `core.render_effect(effect, t)`,
used by both the GUI previews and the agent's `Animator` thread (writes frames to the LEDs at the configured fps).
`core.normalize_effect` must stay tolerant of bad input. Presets live in `core.PRESETS`.

Icons: badges are Lucide line icons embedded in `gui.ICONS` (inner SVG, rendered by
`icon_pixmap`, ISC notice kept beside them). `monogram_badge(name, color)` takes an icon name; catalog
items map through `ITEM_ICONS` / `CATEGORY_ICONS`. Never use text abbreviations for badges (the owner's call);
add new icons from github.com/lucide-icons/lucide `icons/*.svg`.

**Performance (ideas from CachyOS and Bazzite):** Tools → Performance (`PerformancePage`).
- **Game Boost** (`config["performance"]["boost"]`, off by default): the agent's `update_boost` switches the CPU
  energy preference while `GameWatcher` sees a game (plugged in `performance`, battery `balance_performance`),
  via power-profiles-daemon when it runs (`ppd`, never on battery) or the EPP sysfs files (`epp`, permission by
  `boost_permission_cmd`, key `boost-perms`, tmpfiles `z` rule). `boost_restore` only puts the old value back if
  ours is still set (never fight SteamOS). The undo record is in `BOOST_STATE`, so a crash or SIGTERM can't
  leave the CPU boosted (`recover_boost` at start, `Stopped` + `end_boost` on exit; keep exit code 1 for the
  rollback restart). Report uploads wait until no game runs. TDP/GPU stay with SteamOS: don't add them.
- **Tune-up** (one job, keys `tuneup` / `tuneup-undo`): zram (own script + unit, skipped if zram swap exists),
  `MEM_SYSCTLS`, zram-only swap sysctls (written only if zram came up), THP always + defer+madvise, split-lock
  off, NTSync. `tuneup_plan()` skips what the kernel lacks. `TUNEUP_BEFORE` snapshot lets Undo restore values
  without a reboot. Everything is in `/etc`; the uninstaller removes it.
- **Every game**: `GAME_ENV_OPTIONS` written to `~/.config/environment.d/90-allyhub-games.conf` (no sudo,
  plain KEY=VALUE); Game Mode is a systemd user session so Steam and games inherit it after a restart.
  `game_env_live` reads Steam's `/proc/<pid>/environ` to confirm. FSR 4 uses `PROTON_FSR4_UPGRADE=1` (GE-Proton
  and Proton-CachyOS; `PROTON_FSR4_RDNA3_UPGRADE` does nothing). On the Z2 Extreme FSR 4 is a quality upgrade with
  a frame cost, not a speed-up: say so in UI text. If the owner reports "Waiting for a restart" persisting after a
  reboot, environment.d isn't reaching Game Mode: fall back to `~/.config/gamescope-session/` or launch options.
- **Gaming scheduler (scx_lavd) is NOT built.** SteamOS doesn't ship it, and shipping a scheduler binary that
  runs as root is the owner's decision, not a maintenance-run decision. Don't add it unless the owner explicitly says so.

**Frame generation plugins (the owner's call):** catalog items `lsfg` (decky-lsfg-vk) and `framegen`
(Decky-Framegen) install like Bazzite's `ujust get-decky-lossless-scaling` / `get-framegen`: the GitHub
`releases/latest` asset (stable only, never pre-releases or the Decky store's older copy) via
`github_decky_install_cmd`, which replaces older copies by plugin.json name only after the download worked.
The store only shows UPDATE when its version is newer (`plugin_newer`).

**Controller scrolling:** `GamepadNav.move` scrolls the page by most of a screen when the next
control is far away or missing (`_too_far`), so read-only content is reachable; the right stick (js axis 4)
scrolls freely (`_stick_scroll`). Never scroll the window behind a dialog. Pages must live in `scroll_page`.

**Launchers page (the owner's call):** Install → Launchers (`LaunchersPage`) instead of NSL's own GUI.
`nsl_install_cmd` downloads NSL's script and runs it with launcher names as arguments (its Decky plugin's
method) and a job-scoped `zenity` stand-in (`NSL_ZENITY`): progress lines go to Activity, questions get "no".
Only names in `NSL_GROUPS` are passed. The catalog card opens the page.
NSL scans for launchers at the START of its run (NSLGameScanner.py adds shortcuts through Steam's CEF debugger),
so the job restarts `nslgamescanner.service` (or runs the scanner) afterwards. The full run is in `NSL_LOG`;
`LaunchersPage.job_done` checks `nsl_results` (files + shortcuts.vdf) and reports with `nsl_log_tail()`.
`is_self_game` keeps Ally Hub's own library entry from counting as a game.
NSL can guess the wrong Steam account (env_vars steamid3), and then NSLGameScanner exits with "shortcuts.vdf
does not exist" forever. `_nsl_prep_shell` rewrites steamid3 from `steam_user_id3()` (loginusers MostRecent),
makes shortcuts.vdf exist and executable (the scanner WIPES a non-executable one; real file backed up to
`DATA_DIR/shortcuts.vdf.bak`), then the job runs the scanner itself. Fallback: `cef_add_shortcuts` adds the
same shortcut NSL would (`nsl_shortcut_spec`) via SteamClient.Apps over Steam's local CEF debugger
(127.0.0.1:8080, opened by Decky; stdlib websocket in core, localhost only). Web picks must also pass "Google
Chrome" to NSL. Uninstall = NSL "Uninstall <name>" args (Ubisoft is "Uplay") + `cef_remove_shortcuts`.
Leftovers: `nsl_leftovers` / `nsl_clean_cmd` (home-folder paths only; the shared prefix only when no store is
left in it, unticked by default because games live there). Battle.net through Launchers still needs the
owner's confirmation that it shows up in Game Mode.

**Library art (the owner's call: no SteamGridDB):** Install → Launchers → Library art. `core.art_plan`
lists tiles (`steam_shortcuts`: CEF `appStore` ids merged with shortcuts.vdf) whose grid folder has no portrait.
Icons come out of the tile's .exe (`pe_icon_entries`, `_dib_to_png`, stdlib PE/PNG code); `art_svgs` draws
portrait/wide/hero/logo as SVG using only QtSvg-safe features (no filters, no nested svg); the GUI rasterizes them
one tile per event-loop turn (`_art_step`) and `apply_art` writes `{id}p.png`, `{id}.png`, `{id}_hero.png`,
`{id}_logo.png` to the grid folder and sends them live (`SetCustomArtworkForApp`, asset types 0 portrait,
1 hero, 2 logo, 3 wide; `SetShortcutIcon` with a PNG in `ART_DIR`). Ownership: `art_made` stores a hash per
picture; Ally Hub only replaces a picture while the file still matches its hash (`art_is_ours`), never the
owner's own art, kind by kind. "Use my own picture" passes `mine=True` (always written, never remembered).
Runs after a successful launcher install and after "Add Ally Hub to Steam". Brand logos are never drawn:
the only real artwork used is the program's own icon from the owner's installed copy.

**Game settings (Tools → Games, `GamesPage`):** launch options as switches (`GAME_TOGGLES`: env tokens before
`%command%`, `~/lsfg` as a wrapper), Proton per game, and "Game won't start?" (other Proton, `PROTON_LOG` + send
`proton_log`, `reset_prefix_cmd` renames compatdata/<id> to `<id>_allyhub_backup_<ts>`, steam://validate).
Read/write only through Steam (`game_settings`: RegisterForAppDetails strLaunchOptions/strCompatToolName;
`apply_game_settings`: SetAppLaunchOptions/SpecifyCompatTool); files are the read-only fallback. Rules: switches
only edit options `launch_parseable` accepts (else the text is saved back untouched); only our exact tokens are
removed; unchanged options are sent back byte for byte. For a non-Steam tile, "" Proton means no tool at all.
The page swaps list/detail views in one layout: never open a dialog from inside another (nested = new window).

**Storage saver (Tools → Storage, `StoragePage`):** `storage_scan` sizes games (manifest SizeOnDisk + shader
cache + prefix) and lists leftovers: shader caches/prefixes/downloads of removed games, reset backups, Proton
builds no game uses (keeps the newest per family), the trash. `storage_clean_cmd` re-checks everything at delete
time (`_storage_safe`): never an installed game's or non-Steam tile's prefix (incl. apps listed for unmounted SD
cards, `library_app_ids`), never a Proton in use (`tools_in_use_folders`: folder name, compatibilitytool.vdf ids,
symlink targets), never symlinks or `..`. Prefixes can hold saves: they start unticked.

**Turning things off (the owner's call: never stuck with a faulty add-on):** Decky plugins turn off/on without
uninstalling through Decky's own list (`disabled_plugins` in ~/homebrew/settings/loader.json, plugin.json names;
`decky_toggle_cmd` stops Decky, edits it as root, starts Decky). Catalog cards and store rows have Turn off/on;
the Plugin store page lists every installed plugin (`StorePage.show_mine`) with on/off and Remove, plus safe mode
(`DECKY_SAFE_MODE` remembers what "Turn all plugins off" turned off). Launchers: "Hide from Steam" removes tiles
only; Add restores tiles directly when the launcher is still installed (`LaunchersPage.restorable`). Every new
catalog item needs a working Remove (EmuDeck uses its own uninstall.sh).

**First run (the owner's call: a straightforward, uniform setup for everyone):** install.sh calls
`allyhub.py --first-install` (`core.first_install`), which only acts when no config exists yet: agent on
(`start_agent`), Ally Hub added to Game Mode (`core.add_to_steam`, steamos-add-to-steam), `setup.done = False`.
The GUI then opens Home → Setup (`SetupPage`, steps redraw inside one page: welcome, password, Game Mode +
helper, essentials the user picks, lighting (only with ring LEDs), favorites, reports (only when a report key is
saved, i.e. the owner's device), done). Home shows "Finish setting up" (`core.setup_checklist`) until done or
hidden. Existing installs default to `setup.done = True`. Keep every new first-time requirement in this flow.
**Sudo password (1.3.3, the owner hit a loop: setup reopened passwd after the password was set):** never trust a
cached `state["password"]`. `Hub.refresh_password` re-checks (`passwd -S`; only NP/L/LK count as "none", anything
unclear is None and never blocks), `needs_password` re-checks before asking and offers "Create a password" or
"I already have one" (`setup.password_known`, which overrides a "no"), `on_job_finished` re-checks. Konsole is
started detached with `--separate` and its pid watched (`_pw_timer`), so closing Ally Hub never kills it.

**Save time machine (Tools → Saves, `SavesPage`):** the agent's `tm_snapshot` runs Ludusavi when a game
starts (`config["saves"]`: time_machine, keep) into `TM_DIR` with `--full-limit keep --differential-limit 0`,
at most once per game per 10 minutes, niced. Titles: `ludusavi_title` (Steam id, then exact/normalized name,
never fuzzy); only a clear `errors.unknownGames` answer is cached as unknown. Restore (`tm_restore_cmd`) first
backs up current saves to `TM_BEFORE_RESTORE` and only restores if that worked (`&&`); "Undo the last restore"
restores from there. Never restore while that game runs.

**Sleep guardian (Tools → Sleep, `SleepPage`):** the agent's `update_sleep` takes a light snapshot every second
(suspend_stats + `wakeup_count` per source) and treats a CLOCK_BOOTTIME vs CLOCK_MONOTONIC gap over 5 s as a sleep
(`sleep_entry`: drain, %/h, sources whose wakeup_count rose or `pm_wakeup_irq`, total_hw_sleep share). A rise in
suspend_stats/fail without a gap is a failed sleep. `sleep_findings` flags heavy drain, repeat short wakes and
failures. The only fix writes `NOWAKE_RULE` (USB devices only, never a root hub or non-USB device such as the power
button); the saved list changes only after the job worked, and "Allow again" re-enables wakeup immediately.

**Quick Access panel (Tools → Games card):** a Decky plugin embedded in core.py (`QAM_PLUGIN_JSON`, `QAM_MAIN_PY`,
`QAM_INDEX_JS`; bump `QAM_VERSION` when they change) so normal updates deliver it; `qam_install_cmd` copies it
into ~/homebrew/plugins/AllyHub with sudo and restarts plugin_loader. The frontend is plain ESM on window.SP_REACT /
window.DFL and Decky's loader handshake (`connect(2, "Ally Hub")`, the same one @decky/api uses; npm is blocked
here, so no build step). Its backend only talks to the agent's Unix socket `CONTROL_SOCK` (0600, this user):
`{"op": "status"}` / `{"op": "action", ...}` handled by `Agent.qam_status` / `qam_action` (boost, preset, lights,
brightness, game_flag, backup). Config writes are serialized by `core._CONFIG_LOCK`. Never add network access to it.
Messages that arrive while a pop-up is open wait for it (`_wait_for_sheet`).

**Bar position (the owner's call):** `config["theme"]["bars"]` = "top" (default) or "sides".
`Hub.arrange_bars` rebuilds only the layouts of `top_frame` / `footer_frame` / the central widget (widgets are
kept), so it switches live. In "sides" GamepadNav enters pages with RIGHT and returns to tabs with LEFT.
NEVER `QWidget().setLayout(old)` to drop a layout: Qt reparents the layout's widgets to the
throwaway widget and they die with it. `arrange_bars` builds fresh inner containers, moves widgets in, then
hides + deleteLater()s the empty old ones, and restores focus. Sides are icon only (`TAB_ICONS`, `FOOT_BUTTONS`,
the owner's call). Mock-Qt can't see ownership bugs: get a review before shipping Qt reparenting changes.

**Baseline rules (the owner's call):**
- **Everything must work with the controller in Game Mode.** New widgets need a GamepadNav path (D-pad/A/B,
  Left/Right for value widgets). Combos step with Left/Right unless `setProperty("padCycle", False)`.
- **No separate pop-up windows.** Use `run_dialog(dlg)` (in-window panel over a dimmed page) and the helpers
  `msg_info/msg_warn/msg_error`, `ask`, `ask_text`, `ask_item`, `ask_color`/`pick_color`. Never call
  `QMessageBox.information(...)`, `QInputDialog.get*`, `QColorDialog.getColor` or `dlg.exec()` directly (tests
  enforce this). While `hub._sheet` is set, GamepadNav stays inside it and page shortcuts are ignored.
- **One instance** (`single_instance`, QLocalServer `allyhub-<uid>`); `restart_app` closes the server first.
- **Bottom bar off by default** (`theme.footer`); without it status/progress/Report sit in the header.
- Qt ownership/event-loop changes can't be caught by mock-Qt: always get a review agent pass before shipping.

Qt layout gotcha: a `QPushButton` with a child layout (tiles, preset cards,
theme cards) does NOT grow to fit its contents, AND the app stylesheet's `QPushButton { min-height }` is
re-applied on every polish, overwriting `setFixedHeight`/`setMinimumHeight`. Use `CardButton` for any
button that hosts a layout: it pins its size and re-pins after Polish/StyleChange. The mock-Qt tests
can't catch visual sizing problems, so describe size assumptions in comments.

Lighting writes: software effects need the LED's hardware `effect`/`mode` attribute in its plain-color
option (`core.static_mode`), otherwise the hardware ignores `multi_intensity`. Only color and brightness
writes are required; mode writes are best effort. **Test lights** files a `lighting` report with
`core.lighting_diagnostics()` (full sysfs LED inventory) when the rings don't respond: use it to adapt
`find_leds`/`rgb_writes` to the real hardware.

Installed layout on the device: code in `~/.local/share/allyhub/` (same dir holds data: `allyhub.log`,
`update_state.json`, `reports/`, `previous/`), config in `~/.config/allyhub/config.json`.

## SteamOS facts that shape the code

- Root filesystem is read-only. Never use pacman or write outside `$HOME`, `/etc` (overlay) or `/sys`.
- Anything needing root goes through the job runner, which uses a `sudo -A` shim and a kdialog password prompt.
- User may have no sudo password set; check `state["password"]` / `needs_password()` first.
- Handheld Daemon refuses to install on SteamOS by design. Do not re-add it. Ally Center is the replacement.
- SteamOS 3.8+ natively supports the Ally X controller, TDP and audio. Don't fight it.
- Joystick ring LEDs (when the kernel exposes them) are `/sys/class/leds/*:rgb:*` multicolor devices.
  On the owner's Ally X (SteamOS 3.9, kernel 7.2 neptune) it's `ally:rgb:joystick_rings` with
  `multi_index` = `rgb rgb rgb rgb`: **four zones, each one packed 0xRRGGBB value** (see `PACKED_CHANNELS`,
  `channel_value`), plus `multi_max_intensity` and a `sleep_animation` enum. Never assume red/green/blue channels.
  Packed channels have selectable encodings (`LIGHT_ENCODINGS`: packed, packed_bgr, clamped), saved per device
  as `config["lighting"]["encoding"]` by the **guided light test** (Lighting page → Test lights). Its report
  is a table of encoding / expected color / color the owner saw / values written / kernel readback: read it
  before changing LED code. Clamping to `multi_max_intensity` turns red/green blue.
  On the owner's kernel `multi_max_intensity` is 255 and the kernel silently caps every zone at 255, so sysfs
  can only ever show blue. Hence the **direct HID** path (`encoding == "hid"`):
  ASUS 0x5A packets (init "ASUS Tech.Inc.", brightness 0xBA, mode 0xB3 per zone, set 0xB5, apply 0xB4) to
  the hidraw node behind the LED (`led_hidraw`), permission via `70-allyhub-hid.rules`. Chip-mode effects
  (`hid_effect_packets`) are sent ONCE per change (0xB5 may write the chip's memory); the only per-frame HID
  path is zone streaming described above.
- Installers often exit 0 when they refuse to run; the GUI re-checks the item afterwards.

**Privacy rule (the owner's call): never write the owner's real name anywhere**: code, comments, docs, UI text,
commit messages, issue comments, replies, labels, release notes. Call them "the owner", "the developer" or
`Ravenor907`. Commits are authored as Claude (git config), never with the owner's name or email.

## Who decides what

Ally Hub is **the owner's personal project**. It's public so others can use it, but the owner alone decides what the
app does. Three sources of work, handled differently:

| Source | What to do |
|---|---|
| `auto-report` issues from the owner's device | Fix automatically (routine below) |
| Issues or comments from **the owner** (`Ravenor907`) | Treat as instructions. Implement requests that are clear and testable |
| Issues, comments or PRs from **anyone else** | Reply, triage, summarize for the owner. **Never change app behavior for them unless the owner approved it** (he adds the `approved` label or comments approval) |

For other people's **bug reports**: reply within the daily run, ask for missing details (version, SteamOS
version, Activity log), try to reproduce. If it's a clear bug that also affects the owner's setup (crash,
broken install command, wrong detection), you may fix it like an auto-report. Anything that changes
features, defaults, UI or the catalog needs `approved`.

For **suggestions**: thank them, restate the idea in one line, say the owner will review it, add the
`suggestion` label. Never promise it will happen. If the owner labels it `approved`, implement it in a later run.
If he labels it `wontfix` or says no, close it kindly with his reason if he gave one.

For **pull requests** from others: never merge. Review them (does it pass tests, is it safe), comment
with a short summary, and list them for the owner. The owner merges himself.

### Replying to people

- Friendly, brief, plain language, helpful. No em dashes.
- Write in first person plural or neutral voice, and end every reply to someone other than the owner with:
  `<sub>Replied by Claude, Ally Hub's AI maintainer.</sub>` People should know who they're talking to.
- Point people to Ally Doctor and the Activity log when relevant.
- Never share anything about the owner beyond what's in the repo. Never ask anyone for passwords or keys.
- Don't argue. If someone is hostile or spamming, don't engage; mention it to the owner.
- Close stale issues (no reply 14 days after asking for details) with a polite note.

### Labels

Make sure these exist (create them if missing): `auto-report`, `bug`, `suggestion`, `approved`,
`needs-owner`, `question`, `wontfix`, `duplicate`.

## Branches and update channels (the owner's call)

- `main` is **Stable**: what every device gets. `testing` is the owner's **test builds**: devices whose
  Settings → Updates → Update channel is Testing (`config["updates"]["channel"]`) install whichever of main and
  testing has the higher build (`check_for_update`, `UPDATE_CHANNELS`). Stable devices never look at testing.
- New features go to `testing` first. They reach `main` only when the owner says to ship them.
- The testing branch's VERSION must always be **higher** than main's (e.g. main 6.1.4, testing 6.2.x), or test
  devices fall back to main. Never delete the `testing` branch: test devices follow it.
- Reports from test builds carry the `testing` label and "(testing)" in the version line. Fix those on `testing`
  (bump its patch number) unless the bug is also on main.
- Any fix released on `main` is merged into `testing` the same run (keep testing's higher VERSION, merge the
  changelog entries).
- Shipping ("ship it"): merge testing into main (main takes testing's VERSION and changelog), push main, then
  reset testing to main so the next test cycle starts from the release.
- Leaving Testing: the Updates page offers the stable build (`install_update(..., allow_older=True)`, only ever
  the exact stable version). Keep that path and the rollback intact.

## Daily maintenance routine

1. Read all open issues and PRs in `Ravenor907/AllyHub`, plus new comments since the last run. Fetch both
   `main` and `testing`; see "Branches and update channels" for which branch a fix belongs on.
2. Triage each auto-report (and approved items):
   - **Code bug in Ally Hub** → fix it, add a regression check to `tests/run_tests.py` when practical.
   - **Third-party installer or network failure** (Decky CDN down, Flathub outage, upstream script changed)
     → if Ally Hub can work around it (new URL, retry, better detection, clearer message), do that;
     otherwise comment with the explanation and close it.
   - **Needs the owner** (hardware-specific, unclear, or a judgment call) → comment with a short question, add
     label `needs-owner`, leave it open, and mention it in the summary.
   - Duplicates → close pointing at the original.
3. Run `python3 tests/run_tests.py`. **Never push if any section fails.** Fix or revert first.
4. Release: bump the patch number in `VERSION` (6.0.0 → 6.0.1; minor bump only for real features),
   add a `## x.y.z` section at the top of `CHANGELOG.md` written for the owner (plain language, one line per fix),
   update the version in the README badge (`badge/version-X.Y.Z-`), commit, push to `main`.
   **Commit titles stay short** (`Release 1.0.3`, `Fix lighting after sleep`): GitHub shows the latest
   title next to every file and folder on the repo page, and the owner wants that page minimal. Details go in
   the commit body.
   **Two version numbers:** `VERSION` is the updater's build number and must only go
   up (installed copies update only to a higher number). People see the public number = build with 5 off
   the first part (`core.display_version`): build 6.0.1 → **1.0.1**, 6.1.0 → 1.1.0. CHANGELOG headings,
   the README badge, release names and anything user-facing use the public number; never show the build
   number except in reports ("1.0.1 (build 6.0.1)").
   Devices pick it up within a day. (Tags can't be pushed from Claude's sessions; don't try.)
5. On each fixed issue, comment what changed and the version, then close it.
6. Reply to everyone else per "Who decides what".
7. If nothing needs fixing, don't bump the version or push code.
8. Finish with a short summary for the owner: what shipped, who wrote in, suggestions waiting for his
   decision (with links), anything labeled `needs-owner`.

## Keeping the repo sleek

- README stays short and scannable: banner, badges, highlights table, install one-liner, controller
  table, notes. Update the highlights when features change. Keep `assets/banner.svg` in sync with the
  app's look.
- Issue templates live in `.github/ISSUE_TEMPLATE/`. Keep them short.
- No clutter in the repo root: README.md, LICENSE, VERSION and the folders only (tested).

## Guardrails

- Never weaken: privacy scrubbing (`core.scrub`), PIN auth on the phone remote, the update rollback
  (`startup_check` / `mark_healthy` / `rollback`), or the syntax check in `install_update`.
- Never add telemetry, network calls to new hosts, or anything that sends data anywhere except the
  existing GitHub issue reports (which are opt-in).
- Never change the update source (`REPO_DEFAULT`, `main` branch) or the files list in `APP_FILES`
  without making sure installed copies can still update.
- Keep the config schema backwards compatible: add keys to `DEFAULT_CONFIG`, never rename or remove.
- One release per day at most. Keep changes focused on the reported problems; no drive-by refactors.
- Keep each run's scope small
- User-facing text: friendly, short, no jargon. Don't use em dashes in user-facing text.

## Reports format

**The owner wants little troubleshooting time:** read the issue AND its comments first; the comments
hold `<details>` attachments: "Full job output" (complete task log from `JOB_LOG_DIR`), "System snapshot"
(`diagnostics_snapshot()`: Steam account, CEF debugger, Decky + plugin versions, Proton builds, performance,
lighting, launchers, redacted config, agent journal) and "Ally Hub log (last 300 lines)" (includes `job
started/finished` and `page:` breadcrumbs). Usually enough to fix without asking the owner anything.
- `[report] ...` issues (kind `user`) come from the owner's **Report a problem** button: his own words, so treat them like
  an issue from the owner (instructions). They send even with automatic reports off (still needs the access key).
- Reports upload immediately (`upload_soon`, a flock serializes GUI and agent). Repeats are keyed per fingerprint AND
  version (`REPORT_REPEAT_S`), so a problem that survives a fix shows up again at once as "Happened again".
- When adding a feature, add `queue_report` calls at its failure points with `attachments=[...]` holding the full
  output; silent failures cost the most time.

Issue bodies contain: kind (`crash`, `install-failure`, `rollback`, `lighting`, `test`), a fingerprint, the environment
(Ally Hub version, SteamOS version/build, kernel, device, mode), scrubbed details/traceback and the last
lines of `allyhub.log`. "Happened again" comments are added to the same issue instead of new issues.
Close `test` reports immediately.
