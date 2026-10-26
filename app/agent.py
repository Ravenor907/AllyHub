"""
Ally Hub agent: a small background service (systemd --user) that runs in both
Desktop and Game Mode.

- Lighting: restores your color at login, battery-level rings, low-battery
  flash, per-game colors, dock-mode lighting
- Dock mode: switches audio to the TV/monitor when you plug into a display
- Health log: battery, power draw, temps and the running game every minute
- Update Guardian: notices SteamOS updates and a missing Decky Loader,
  takes a daily snapshot of your settings
- Auto save backups through Ludusavi
"""

import json
import math
import os
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path

import core

ALERTS_FILE = core.DATA_DIR / "alerts.json"
SEEN_FILE = core.DATA_DIR / "seen_games.json"
SNAP_DIR = core.SETTINGS_SNAP_DIR
HEALTH_KEEP_DAYS = 7


def log(msg: str):
    print(time.strftime("%H:%M:%S"), msg, flush=True)
    core.app_log("agent", msg)


def add_alert(alert_id: str, text: str, notify: bool = True):
    alerts = core.read_json(ALERTS_FILE, []) or []
    if any(a.get("id") == alert_id for a in alerts):
        return
    alerts.append({"id": alert_id, "text": text, "ts": time.time()})
    core.write_json(ALERTS_FILE, alerts)
    log(f"alert: {text}")
    if notify and shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-a", "Ally Hub", "Ally Hub", text],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


snapshot_settings = core.snapshot_settings     # moved to core in 1.4.0 (the GUI's Back up now uses it too)


# --------------------------------------------------------------------------
# Lighting decision
# --------------------------------------------------------------------------

def desired_lighting(cfg: dict, battery: dict, game: str, docked: bool, tick: int = 0):
    """Return (effect, brightness, enums, reason) or None to leave LEDs alone."""
    a = cfg["agent"]
    base = cfg.get("rgb") or {}
    base_b = int(base.get("brightness", 255))
    enums = base.get("enums", {})
    mine = core.base_effect(cfg)
    pct = core.read_int(battery.get("path", Path("/x")) / "capacity") if battery else None
    status = battery.get("status", "") if battery else ""

    def static(rgb):
        return core.normalize_effect({"type": "static", "colors": [core.rgb_to_hex(rgb)]})

    if a.get("low_battery_flash") and pct is not None and pct <= 15 and status == "Discharging":
        return (core.normalize_effect({"type": "strobe", "colors": ["#ff0000"], "speed": 0.5}),
                255, {}, "low battery")
    if base and base_b == 0:
        return (mine or static((0, 0, 0)), 0, enums, "lights off")
    if a.get("dock_mode") and docked:
        mode = cfg["dock"].get("lights", "off")
        if mode == "off":
            return (mine or static((0, 0, 0)), 0, enums, "docked: lights off")
        eff = core.lookup_effect(mode, cfg)
        if eff:
            return (eff, base_b or 255, {}, "docked")
    if a.get("game_colors") and game and game in cfg.get("game_colors", {}):
        eff = core.lookup_effect(cfg["game_colors"][game], cfg)
        if eff:
            return (eff, base_b or 255, {}, "game lighting")
    if a.get("battery_rings") and pct is not None:
        color = core.rgb_to_hex(core.battery_color(pct))
        if status == "Charging":
            eff = core.normalize_effect({"type": "breathe", "colors": [color], "speed": 0.9, "param": 0.45})
        else:
            eff = static(core.battery_color(pct))
        return (eff, base_b or 255, {}, "battery rings")
    if mine:
        return (mine, base_b, enums if not core.is_animated(mine) else {}, "your lighting")
    return None


class Animator(threading.Thread):
    """Renders the current lighting effect onto the LEDs at a steady frame rate."""

    def __init__(self, agent):
        super().__init__(daemon=True)
        self.agent = agent
        self.lock = threading.Lock()
        self.spec = None          # (effect, brightness, enums)
        self.spec_key = None
        self.changed = threading.Event()
        self.last_frame = None
        self.ok = True
        self.started_at = time.monotonic()
        self.clock_offset = None  # wall clock minus monotonic: jumps when the handheld wakes up

    _fps, _fps_at = None, 0.0

    def set(self, effect, brightness, enums):
        key = json.dumps([effect, brightness, enums], sort_keys=True)
        with self.lock:
            if key == self.spec_key:
                return
            self.spec, self.spec_key = (effect, brightness, enums), key
            self.last_frame = None
            self.started_at = time.monotonic()
        self.changed.set()

    def fps(self) -> float:
        light = self.agent.cfg.get("lighting") or {}
        try:
            fps = max(5, min(30, int(light.get("fps", 20))))
        except (TypeError, ValueError):
            fps = 20
        bat = core.battery_info()
        if bat.get("status") == "Discharging" and light.get("on_battery", "slow") == "slow":
            # two thirds of the chosen rate, never below the old 15 (30 -> 20, 20 -> 15, 10 stays 10). It was a flat
            # 15 cap, so on battery Smooth and Silky looked exactly the same (the owner, 1.4.1)
            fps = max(min(fps, 15), round(fps * 2 / 3))
        return fps

    def _timed(self, send, animated: bool) -> bool:
        """Send a frame and, while animating, log the real frame rate once a minute (the owner's videos showed
        about 3 fps when the setting said 20: this line in the log says what the rings actually get)."""
        t0 = time.monotonic()
        ok = send()
        if not animated:
            return ok
        st = getattr(self, "_stat", None)
        if st is None or t0 - st[2] > 90:                 # first frame, or animation was paused: start over
            st = self._stat = [0, 0.0, t0]
        st[0] += 1
        st[1] += time.monotonic() - t0
        if t0 - st[2] >= 60 and st[0]:
            log(f"lighting: {st[0] / (t0 - st[2]):.1f} frames a second, {st[1] / st[0] * 1000:.0f} ms to send each")
            self._stat = [0, 0.0, t0]
        return ok

    def run(self):
        reported = False
        while True:
            try:
                self.step()
            except Exception:
                # never let one bad frame kill the lights for the rest of the session
                self.ok = False
                if not reported:
                    reported = True
                    log(f"lighting frame failed: {sys.exc_info()[1]!r}")
                    core.report_exception("agent-animator")
                self.changed.wait(2.0)
                self.changed.clear()

    def step(self):
        with self.lock:
            spec = self.spec
        if spec is None:
            self.changed.wait(1.0)
            self.changed.clear()
            return
        effect, brightness, enums = spec
        light = self.agent.cfg.get("lighting") or {}
        offset = time.time() - time.monotonic()
        if self.clock_offset is not None and abs(offset - self.clock_offset) > 20:
            # woke from sleep: the chip may have reset and Dynamic Lighting may be back, so send again
            log("woke from sleep, re-sending lighting")
            self.last_frame = None
            core.hid_reset_session()    # redo the full first-time sequence on the chip
            self.agent.leds = core.find_leds() or self.agent.leds
        self.clock_offset = offset
        streaming = (light.get("encoding") == "hid" and core.hid_streams(light.get("hid_method"))
                     and not core.chip_runs(effect, brightness))
        if light.get("encoding") == "hid" and not streaming:
            # Direct HID: the chip runs the effect itself. Send once per change, never per frame.
            key = ("hid", json.dumps(effect, sort_keys=True), brightness, light.get("hid_method"))
            if key != self.last_frame:
                if core.hid_apply_effect(effect, brightness, self.agent.leds, light.get("hid_method")):
                    self.last_frame = key
                    self.ok = True
                else:
                    fresh = core.find_leds()
                    if fresh and [l.path for l in fresh] != [l.path for l in self.agent.leds]:
                        self.agent.leds = fresh
                        return
                    self.ok = False
                    self.changed.wait(5.0)
                    self.changed.clear()
                    return
            self.changed.wait(2.0)
            self.changed.clear()
            return
        bat_static = (light.get("on_battery") == "static"
                      and core.battery_info().get("status") == "Discharging")
        animated = core.is_animated(effect) and not bat_static
        t = time.monotonic() - self.started_at
        if streaming:
            # Every effect drawn here, frame by frame, as bare zone commands (HueSync's custom path)
            zones = core.zone_frames(effect, t if animated else 0.0)
            if not animated and effect["type"] not in ("static", "spiral") and effect["colors"]:
                zones = [core.hex_to_rgb(effect["colors"][0])] * 4
            elif animated:
                # blend toward the new colors instead of jumping (the rings have only 4 zones, so a jump shows)
                prev = getattr(self, "_zones", None)
                if prev and len(prev) == len(zones):
                    zones = [tuple(int(round(p + (c - p) * 0.55)) for p, c in zip(pz, z)) for pz, z in zip(prev, zones)]
            self._zones = zones
            key = ("zones", tuple(zones), brightness)
            send = lambda: core.hid_zone_frame(zones, brightness, self.agent.leds, light.get("hid_method"),
                                               light.get("gamma"), light.get("stream_all", True) is not False)
        else:
            frame = core.effect_frame(effect, t if animated else 0.0)
            if not animated and effect["type"] != "static":
                frame = core.hex_to_rgb(effect["colors"][0]) if effect["colors"] else frame
            key = (frame, brightness)
            send = lambda: core.apply_lighting(frame, brightness, enums, self.agent.leds, light.get("encoding"))
        if key != self.last_frame:
            if self._timed(send, animated):
                self.last_frame = key
                self.ok = True
            else:
                # The rings' USB device re-appears after sleep, so the old sysfs paths can go
                # stale. Look again before deciding it's a permission problem.
                fresh = core.find_leds()
                if fresh and [l.path for l in fresh] != [l.path for l in self.agent.leds]:
                    log("lighting devices changed, rescanning")
                    self.agent.leds = fresh
                    return
                self.ok = False
                self.changed.wait(5.0)      # no permission: back off
                self.changed.clear()
                return
        if animated:
            now = time.monotonic()
            if now - self._fps_at > 5 or self._fps is None:      # battery state is read every few seconds, not per frame
                self._fps, self._fps_at = self.fps(), now
            fps = min(self._fps, core.STREAM_FPS_MAX) if streaming else self._fps
            # pace by deadline: the time spent sending this frame counts toward the frame, so 20 fps is 20 fps
            self._next = max(getattr(self, "_next", now), now - 1.0 / fps) + 1.0 / fps
            if self.changed.wait(max(0.0, self._next - time.monotonic())):
                self.changed.clear()
        else:
            self.changed.wait(2.0)
            self.changed.clear()


# --------------------------------------------------------------------------

class Agent:
    def __init__(self):
        self.cfg = core.load_config()
        self.cfg_mtime = 0.0
        self.wake = threading.Event()
        self.games = core.GameWatcher()
        self.game = None
        self.docked = None
        self.last_led = None
        self.leds = core.find_leds()
        self.led_reason = ""
        self.tick = 0
        self.last_health = 0.0
        self.last_trim = 0.0
        self.last_guard = 0.0
        self.save_proc = None
        self.seen = core.read_json(SEEN_FILE, {}) or {}
        self.state_cache = {}
        self.started = time.time()
        self.healthy = False
        self.net_busy = threading.Lock()
        self.last_upload = 0.0
        self.updated_to = None
        self.animator = None
        self.boost = None          # what Game Boost changed and must put back (see update_boost)
        self.boost_note = ""
        self.boost_tried = None    # last target that changed nothing, so it isn't retried every 3 s
        self.stopping = False      # set by SIGTERM; the loop exits and Game Boost is put back
        self.control = None        # local socket for the Quick Access panel (see serve_control)
        self.backup_now = False
        self._ludusavi, self._ludusavi_t = False, 0.0
        self.qam_game = {}         # the running game's switches, read from Steam once per game
        self.tm_lock = threading.Lock()   # one save snapshot at a time
        self.sleep_last = None     # (monotonic, boottime, battery %, charging) at the previous tick
        self.sleep_pre = None      # wakeup counters / suspend stats from shortly before a sleep

    # ---- config ----
    def reload_config(self):
        try:
            m = core.CONFIG_FILE.stat().st_mtime
        except OSError:
            m = 0
        if m != self.cfg_mtime:
            self.cfg_mtime = m
            self.cfg = core.load_config()
            self.last_led = None   # re-apply
            return True
        return False

    # ---- status and quick actions (the Quick Access panel) ----
    def status(self) -> dict:
        b = core.battery_info()
        s = core.sensors()
        return {
            "battery": core.battery_percent(), "time_left": core.time_left_text(),
            "cpu": s["cpu_temp"], "gpu": s["gpu_temp"], "fan": s["fan_rpm"],
            "game": self.game, "game_name": self.seen.get(self.game) if self.game else None,
            "docked": bool(self.docked), "battery_rings": self.cfg["agent"].get("battery_rings"),
            "wol": bool(core.normalize_mac(self.cfg["wol"].get("mac", ""))),
            "health": b.get("health"),
        }

    def remote_action(self, action: str, data: dict) -> str:
        if action == "rgb":
            try:
                rgb = core.hex_to_rgb(str(data.get("hex", "#e11d48")))
                bright = max(0, min(255, int(data.get("brightness", 255))))
            except (ValueError, TypeError):
                return "Bad color"

            def fn(cfg):
                old = cfg.get("rgb") or {}
                cfg["rgb"] = {"rgb": list(rgb), "brightness": bright, "enums": old.get("enums", {})}
                cfg["lighting"]["effect"] = {"type": "static", "colors": [core.rgb_to_hex(rgb)]}
            self.cfg = core.update_config(fn)
            msg = "Color applied"
        elif action == "preset":
            name = str(data.get("name", ""))
            eff = core.lookup_effect("preset:" + name, self.cfg)
            if not eff:
                return "Unknown effect"

            def fn(cfg):
                cfg["lighting"]["effect"] = eff
                old = cfg.get("rgb") or {"rgb": [225, 29, 72], "enums": {}}
                if not old.get("brightness"):
                    old["brightness"] = 255
                cfg["rgb"] = old
            self.cfg = core.update_config(fn)
            msg = f"{name} on"
        elif action == "lights":
            def fn(cfg):
                old = cfg.get("rgb") or {"rgb": [225, 29, 72], "enums": {}}
                old["brightness"] = 0
                cfg["rgb"] = old
            self.cfg = core.update_config(fn)
            msg = "Lights off"
        elif action == "battery_rings":
            on = bool(data.get("on"))
            self.cfg = core.update_config(lambda c: c["agent"].__setitem__("battery_rings", on))
            msg = f"Battery rings {'on' if on else 'off'}"
        elif action == "game_color":
            if not self.game:
                return "No game is running"
            hexc = str(data.get("hex", ""))
            try:
                core.hex_to_rgb(hexc)
            except ValueError:
                return "Bad color"
            g = self.game
            self.cfg = core.update_config(lambda c: c["game_colors"].__setitem__(g, hexc))
            msg = f"Saved color for {self.seen.get(g, g)}"
        elif action == "wol":
            w = self.cfg["wol"]
            ok = core.send_wol(w.get("mac", ""), w.get("broadcast", ""))
            msg = f"Wake signal sent to {w.get('name') or 'your PC'}" if ok else "Set your PC's MAC address first"
        else:
            return "Unknown action"
        self.last_led = None
        self.wake.set()
        return msg

    # ---- Sleep guardian: a gap between boottime and monotonic time is a sleep ----
    def update_sleep(self, battery: dict):
        mono, boot = time.monotonic(), time.clock_gettime(time.CLOCK_BOOTTIME)
        pct = core.battery_level()
        charging = (battery or {}).get("status") in ("Charging", "Full")
        snap = core.sleep_snapshot(full=False)                  # light: stats and wakeup counters only
        if self.sleep_last and self.sleep_pre:
            lm, lb, lpct, lch = self.sleep_last
            gap = (boot - lb) - (mono - lm)                        # exact: both clocks move together when awake
            if gap > 5:
                post = core.sleep_snapshot()
                post["irq"] = core.wake_irq_name()
                entry = core.sleep_entry(self.sleep_pre, post, gap, lpct, pct, lch or charging)
                core.record_sleep(entry)
                log(f"woke after {core.duration_text(gap)}: battery {entry['drop']}% "
                    f"{'(charging)' if entry['charging'] else ''} woke by {', '.join(entry['woke_by']) or '?'}"
                    f"{' FAILED ' + str(entry['failed_dev']) if entry['failed'] else ''}")
            else:
                f0, f1 = (self.sleep_pre.get("stats") or {}).get("fail"), (snap.get("stats") or {}).get("fail")
                if isinstance(f0, int) and isinstance(f1, int) and f1 > f0:   # a sleep the kernel gave up on
                    core.record_sleep(core.sleep_failure_entry(snap["stats"]))
                    log(f"a sleep failed: {snap['stats'].get('last_failed_dev')} "
                        f"({snap['stats'].get('last_failed_step')})")
        self.sleep_pre = snap
        self.sleep_last = (mono, boot, pct, charging)

    # ---- Save time machine: snapshot a game's saves as it starts ----
    def tm_snapshot(self, game):
        if not self.tm_lock.acquire(blocking=False):
            log("save snapshot skipped: another snapshot is still running")
            return
        try:
            if not self.ludusavi_ready():
                log("save snapshot skipped: Ludusavi isn't installed")
                return
            name = self.seen.get(game) or ""
            appid = core.steam_appid_of(game)
            title = core.ludusavi_title(None if int(game) > 0xFFFFFFFF else appid, name)
            if not title:
                log(f"save snapshot skipped: Ludusavi doesn't know {name or game}")
                return
            if not core.tm_due(title):
                return
            keep = int((self.cfg.get("saves") or {}).get("keep", 5) or 5)
            gentle = (["nice", "-n", "19"] + (["ionice", "-c3"] if shutil.which("ionice") else []))
            core.TM_DIR.mkdir(parents=True, exist_ok=True)
            try:
                rc = subprocess.run(gentle + core.tm_backup_args(title, keep), stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, timeout=900).returncode
            except subprocess.TimeoutExpired:
                rc = -1
            core.tm_record(title, rc, name)
            log(f"save snapshot for {title}: {'done' if rc == 0 else f'failed rc={rc}'}")
        except Exception:
            log(f"save snapshot failed: {sys.exc_info()[1]!r}")
        finally:
            self.tm_lock.release()

    # ---- Quick Access panel (a Decky plugin talks to this socket; only this user can open it) ----
    def serve_control(self):
        path = core.CONTROL_SOCK
        try:
            path.unlink(missing_ok=True)
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            old = os.umask(0o177)                   # the socket is born 0600: no window for other users
            try:
                srv.bind(str(path))
            finally:
                os.umask(old)
            os.chmod(path, 0o600)
            srv.listen(4)
        except OSError as e:
            log(f"control socket failed: {e}")
            self.control = False                    # don't retry every 30 s; the next start tries again
            return
        self.control = srv
        threading.Thread(target=self._control_loop, args=(srv,), daemon=True).start()
        log("quick access socket ready")

    def _control_loop(self, srv):
        while not self.stopping:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            threading.Thread(target=self._control_client, args=(conn,), daemon=True).start()

    def _control_client(self, conn):
        with conn:
            try:
                conn.settimeout(10)
                buf = b""
                while b"\n" not in buf and len(buf) < 65536:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                req = json.loads(buf.split(b"\n", 1)[0] or b"{}")
                if req.get("op") == "status":
                    out = self.qam_status()
                elif req.get("op") == "action":
                    out = self.qam_action(str(req.get("name", "")), req.get("data") or {})
                else:
                    out = {"error": "unknown request"}
            except Exception as e:                   # a bad request never takes the agent down
                out = {"error": f"{type(e).__name__}: {e}"}
            try:
                conn.sendall(json.dumps(out).encode() + b"\n")
            except OSError:
                pass

    def _steam_appid(self, game):
        return core.steam_appid_of(game)

    def read_game_flags(self, game):
        appid = self._steam_appid(game)
        if appid is None:
            return
        st = core.game_settings(appid, "shortcut" if int(game) > 0xFFFFFFFF else "steam")
        if self.game == game:
            self.qam_game = {"game": game, "appid": appid, "live": st.get("live"), "options": st.get("options", ""),
                             "tool": st.get("tool", ""), "flags": sorted(core.launch_flags(st.get("options", "")))}

    def qam_status(self) -> dict:
        s = core.sensors()
        light = self.cfg.get("lighting") or {}
        rgb = self.cfg.get("rgb") or {}
        names = list(core.PRESETS) + list(light.get("custom") or {})
        eff = light.get("effect") or None
        g = self.qam_game if self.qam_game.get("game") == self.game else {}
        watts = core.battery_power_w()
        return {
            "version": core.display_version(),
            "battery": core.battery_percent(), "time_left": core.time_left_text(),
            "watts": round(watts, 1) if watts else None,
            "cpu": s.get("cpu_temp"), "gpu": s.get("gpu_temp"), "fan": s.get("fan_rpm"),
            "game": self.game, "game_name": self.seen.get(self.game) if self.game else None,
            "game_flags": g.get("flags"),
            "game_live": bool(g.get("live")) and core.launch_parseable(g.get("options", "")),
            "game_tool": g.get("tool", ""), "lsfg": core.LSFG_WRAPPER.exists(),
            "boost": bool((self.cfg.get("performance") or {}).get("boost")), "boost_note": self.boost_note,
            "lighting": "huesync" if core.lighting_shelved(self.cfg) else "allyhub",
            "effects": names, "effect": core.effect_label(eff) if eff else "",
            "brightness": int(rgb.get("brightness", 255)),
            "speed": float(eff.get("speed", 1.0)) if eff else 1.0,
            "animated": bool(eff) and core.is_animated(core.normalize_effect(eff)),
            "toggles": {k: bool(self.cfg["agent"].get(k)) for k in self.QAM_TOGGLES},
            "time_machine": bool((self.cfg.get("saves") or {}).get("time_machine")),
            "backup": self.ludusavi_ready(),
            "backup_running": self.save_proc is not None,
            "refresh": {"status": core.refresh_state().get("status"), "max": core.refresh_state().get("max"),
                        "left": core.refresh_left(), "on": bool(core.refresh_installed())},
        }

    def ludusavi_ready(self) -> bool:
        """Ludusavi (the save backup tool) is installed; checked at most once a minute."""
        now = time.time()
        if now - self._ludusavi_t > 60:
            self._ludusavi_t = now
            self._ludusavi = core.run_quiet(["flatpak", "info", core.LUDUSAVI_ID])[0] == 0
        return self._ludusavi

    QAM_TOGGLES = ("battery_rings", "low_battery_flash")      # agent switches the panel may flip (no password)

    def qam_action(self, name: str, data: dict) -> dict:
        if name == "refresh_keep":
            ok = core.refresh_keep()
            return {"ok": ok, "message": "Kept. Steam's slider now goes up to 144 Hz." if ok else "Nothing to keep"}
        if name == "refresh_off":
            core.refresh_request_off()
            return {"ok": True, "message": "Going back to 120 Hz: your handheld restarts."}
        if name == "speed":
            try:
                v = max(0.1, min(4.0, float(data.get("value", 1.0))))
            except (TypeError, ValueError):
                return {"ok": False, "message": "Bad speed"}

            def fn(cfg):
                eff = (cfg.get("lighting") or {}).get("effect")
                if isinstance(eff, dict):
                    eff["speed"] = round(v, 2)
            self.cfg = core.update_config(fn)
            self.last_led = None
            self.wake.set()
            return {"ok": True, "message": ""}
        if name == "toggle":
            key, on = str(data.get("key", "")), bool(data.get("on"))
            if key == "time_machine":
                self.cfg = core.update_config(lambda c: c.setdefault("saves", {}).__setitem__("time_machine", on))
                return {"ok": True, "message": f"Save time machine {'on' if on else 'off'}"}
            if key not in self.QAM_TOGGLES:
                return {"ok": False, "message": "Unknown switch"}
            self.cfg = core.update_config(lambda c: c["agent"].__setitem__(key, on))
            self.last_led = None
            self.wake.set()
            return {"ok": True, "message": ""}
        if name == "boost":
            on = bool(data.get("on"))
            self.cfg = core.update_config(lambda c: c.setdefault("performance", {}).__setitem__("boost", on))
            self.wake.set()
            return {"ok": True, "message": f"Game Boost {'on' if on else 'off'}"}
        if name in ("preset", "lights"):
            return {"ok": True, "message": self.remote_action(name, data)}
        if name == "brightness":
            try:
                b = max(0, min(255, int(data.get("value", 255))))
            except (TypeError, ValueError):
                return {"ok": False, "message": "Bad brightness"}

            def fn(cfg):
                old = cfg.get("rgb") or {"rgb": [225, 29, 72], "enums": {}}
                old["brightness"] = b
                cfg["rgb"] = old
            self.cfg = core.update_config(fn)
            self.last_led = None
            self.wake.set()
            return {"ok": True, "message": ""}
        if name == "game_flag":
            key, on = str(data.get("key", "")), bool(data.get("on"))
            g = self.qam_game if self.qam_game.get("game") == self.game else {}
            if key not in core.GAME_TOGGLES or not g.get("appid"):
                return {"ok": False, "message": "No game to change"}
            if not core.launch_parseable(g.get("options", "")):
                return {"ok": False, "message": "This game's launch options need editing in Ally Hub"}
            if key == "lsfg" and on and not core.LSFG_WRAPPER.exists():
                return {"ok": False, "message": "Install Lossless Scaling Frame Gen first"}
            flags = set(core.launch_flags(g.get("options", "")))
            flags = flags | {key} if on else flags - {key}
            opts = core.set_launch_flags(g.get("options", ""), flags)
            done = core.apply_game_settings(g["appid"], opts, None)
            if "options" not in done:
                return {"ok": False, "message": "Steam didn't take the change"}
            g.update(options=opts, flags=sorted(flags))
            return {"ok": True, "message": f"{core.GAME_TOGGLES[key][0]} {'on' if on else 'off'} next time you start "
                                           f"{self.seen.get(self.game) or 'the game'}"}
        if name == "backup":
            if self.save_proc is not None:
                return {"ok": True, "message": "A save backup is already running"}
            self.backup_now = True
            self.wake.set()
            return {"ok": True, "message": "Backing up your saves"}
        return {"ok": False, "message": "Unknown action"}

    # ---- features ----
    def update_lighting(self, battery: dict):
        if core.lighting_shelved(self.cfg):
            self.led_reason = "handled by HueSync"      # never fight the HueSync plugin
            return
        if not self.leds:
            if self.tick % 30 == 0:
                self.leds = core.find_leds()
            self.led_reason = "no ring lights found"
            return
        if self.animator is None:
            self.animator = Animator(self)
            self.animator.start()
        want = desired_lighting(self.cfg, battery, self.game, bool(self.docked), self.tick)
        if want is None:
            return
        effect, bright, enums, reason = want
        self.animator.set(effect, bright, enums)
        if self.animator.ok:
            self.led_reason = reason
        elif not core.lighting_access_ok(self.leds):
            self.led_reason = "no permission (enable passwordless lighting)"
        else:
            self.led_reason = "can't write to the lights"

    def update_dock(self):
        docked = core.external_display_connected()
        if docked != self.docked:
            first = self.docked is None
            self.docked = docked
            self.last_led = None
            if not first and self.cfg["agent"].get("dock_mode") and self.cfg["dock"].get("audio_hdmi"):
                core.set_hdmi_audio(docked)
            if not first:
                log(f"{'docked' if docked else 'undocked'}")

    def update_game(self):
        g = self.games.scan()
        if g and core.is_self_game(g):      # Ally Hub opened from the library is not a game to boost
            g = None
        if g != self.game:
            self.game = g
            self.last_led = None
            if g and g not in self.seen:
                self.seen[g] = core.game_name(g)
                core.write_json(SEEN_FILE, self.seen)
            log(f"game: {self.seen.get(g) if g else 'none'}")
            self.qam_game = {}
            if g and self.control:
                threading.Thread(target=self.read_game_flags, args=(g,), daemon=True).start()
            if g and (self.cfg.get("saves") or {}).get("time_machine"):
                threading.Thread(target=self.tm_snapshot, args=(g,), daemon=True).start()

    # ---- Game Boost (Tools > Performance) ----
    def recover_boost(self):
        """A boost left behind by a crash or restart is undone at start; it's re-applied if a game runs."""
        rec = core.read_json(core.BOOST_STATE, None)
        if rec:
            core.boost_restore(rec)
            core.BOOST_STATE.unlink(missing_ok=True)
            log(f"game boost: restored {rec.get('before')} after restart")

    def end_boost(self, why: str):
        if not self.boost:
            return
        core.boost_restore(self.boost)
        log(f"game boost off ({why}): back to {self.boost.get('before')}")
        self.boost = None
        core.BOOST_STATE.unlink(missing_ok=True)

    def update_boost(self, battery: dict):
        want = bool((self.cfg.get("performance") or {}).get("boost")) and bool(self.game)
        if not want:
            self.end_boost("no game" if not self.game else "turned off")
            self.boost_note = ""
            self.boost_tried = None
            return
        on_battery = battery.get("status") == "Discharging"
        target = core.boost_target(core.boost_backend(), on_battery)
        if self.boost and self.boost.get("set") == target:
            return
        if not self.boost and self.boost_tried == (self.game, target):
            return
        self.end_boost("power source changed")
        self.boost_tried = (self.game, target)
        rec = core.boost_apply(on_battery)
        if rec:
            self.boost = rec
            core.write_json(core.BOOST_STATE, rec)
            self.boost_note = rec["set"]
            log(f"game boost on for {self.seen.get(self.game, self.game)}: {rec['before']} -> {rec['set']}")
        else:
            cur = core.boost_current(core.boost_backend())
            self.boost_note = cur if cur and cur == target else "unavailable"

    def log_health(self, battery: dict):
        now = time.time()
        if now - self.last_health < 60:
            return
        self.last_health = now
        s = core.sensors()
        w = core.battery_power_w()
        row = {"t": int(now), "pct": core.read_int(battery["path"] / "capacity") if battery else None,
               "st": battery.get("status") if battery else None,
               "w": round(w, 2) if w else None,
               "cpu": round(s["cpu_temp"], 1) if s["cpu_temp"] else None,
               "gpu": round(s["gpu_temp"], 1) if s["gpu_temp"] else None,
               "fan": s["fan_rpm"], "game": self.game}
        core.DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(core.HEALTH_FILE, "a") as f:
            f.write(json.dumps(row) + "\n")
        if now - self.last_trim > 6 * 3600:
            self.last_trim = now
            keep = core.read_health(now - HEALTH_KEEP_DAYS * 86400)
            tmp = core.HEALTH_FILE.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps(r) + "\n" for r in keep))
            os.replace(tmp, core.HEALTH_FILE)

    def keep_current(self, now: float):
        """1.5.0.23 (the owner: "keeps up by default"): once a day, when no game runs, apply the updates that need no
        password (Flatpak apps; Decky plugins Ally Hub installed, whose folders are the user's, with the Decky
        restart permission from Allow all). What needs a password waits for the Checkup's Update all."""
        if self.game or not self.cfg.get("updates", {}).get("keep_current", True):
            return
        st = core.keep_current_state()
        if now - float(st.get("last", 0) or 0) < 86400 or not core.internet_ok():
            return
        st["last"] = now
        core.keep_current_save(st)
        with core.keep_current_lock() as got:      # never at the same time as the window's Update all
            if not got:
                return
            core.store_cache_refresh()
            ups = core.update_registry(refresh=True)
            done, skipped = [], [u["name"] for u in ups if u["needs_root"]]
            for u in ups:
                if u["needs_root"]:
                    continue
                self.safely("game", self.update_game)      # fresh: this runs on the network thread
                if self.game:
                    break
                rc, out = core.run_job(u["cmd"], timeout=900)
                if rc == 0:
                    done.append(u["name"])
                else:
                    log(f"keep current: {u['name']} failed (rc={rc}): {out[-300:]}")
        if done:
            log("keep current: updated " + ", ".join(done))
            add_alert(f"kept-current-{int(now)}", "Updated by itself: " + ", ".join(done) + ".", notify=False)
        if skipped:
            log("keep current: waiting for a password: " + ", ".join(skipped))

    def guardian(self):
        now = time.time()
        if now - self.last_guard < 600:
            return
        self.last_guard = now
        osr = core.os_release()
        build = osr.get("BUILD_ID") or osr.get("VERSION_ID") or ""
        g = self.cfg["guardian"]
        decky = core.DECKY_PATH.exists() and core.decky_service_exists()   # files alone can outlive the service
        changes = {}
        if build and build != g.get("last_build"):
            if g.get("last_build"):
                add_alert(f"update-{build}", f"SteamOS was updated to {osr.get('VERSION_ID', build)}.")
            changes["last_build"] = build
        if decky and not g.get("decky_expected"):
            changes["decky_expected"] = True
        if not decky and g.get("decky_expected"):
            add_alert(f"decky-missing-{build}",
                      "Decky Loader is missing, probably removed by a SteamOS update. "
                      "Open Ally Hub and tap Repair.")
        # 1.5.0.3: once the one-time permission is in place, the panel follows Ally Hub's updates by itself (no
        # password), never during a game (restarting Decky closes the ••• menu for a moment)
        if not self.game and core.qam_outdated() and core.qam_self_updatable():
            ok = core.qam_update_nopw()
            log(f"quick access panel {'updated' if ok else 'update failed'} (no password)")
        if changes:
            self.cfg = core.update_config(lambda c: c["guardian"].update(changes))
            self.cfg_mtime = core.CONFIG_FILE.stat().st_mtime
        n = core.patch_nsl_shortcuts()        # NSL rewrites its desktop files; keep the remembered choice in them
        if n:
            log(f"desktop shortcuts: {n} patched to remember Standalone or Steam")
        snaps = sorted(SNAP_DIR.glob("settings-*.tar.gz"))
        if not snaps or now - snaps[-1].stat().st_mtime > 86400:
            try:
                snapshot_settings()
                log("settings snapshot saved")
            except OSError as e:
                log(f"snapshot failed: {e}")

    def save_backups(self, battery: dict):
        a = self.cfg["agent"]
        if self.save_proc is not None:
            rc = self.save_proc.poll()
            if rc is None:
                return
            st = core.read_json(core.DATA_DIR / "save_backup.json", {}) or {}
            st.update({"last": time.time(), "rc": rc})
            core.write_json(core.DATA_DIR / "save_backup.json", st)
            log(f"save backup finished rc={rc}")
            self.save_proc = None
            return
        now = self.backup_now
        self.backup_now = False
        if not now and (not a.get("save_backup") or self.game or self.tick % 60):
            return
        st = core.read_json(core.DATA_DIR / "save_backup.json", {}) or {}
        if not now and time.time() - st.get("last", 0) < float(a.get("save_backup_hours", 24)) * 3600:
            return
        pct = core.read_int(battery["path"] / "capacity") if battery else 100
        if not now and battery and battery.get("status") == "Discharging" and (pct or 0) < 30:
            return
        if core.run_quiet(["flatpak", "info", core.LUDUSAVI_ID])[0] != 0:
            return
        dest = a.get("save_backup_dir") or str(core.BACKUP_DIR / "saves")
        Path(dest).mkdir(parents=True, exist_ok=True)
        log("starting save backup")
        self.save_proc = subprocess.Popen(
            ["flatpak", "run", core.LUDUSAVI_ID, "backup", "--force", "--path", dest],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def write_state(self):
        st = {"ts": time.time(), "game": self.game,
              "game_name": self.seen.get(self.game) if self.game else None,
              "docked": bool(self.docked), "led": self.led_reason,
              "pid": os.getpid(),
              "boost": self.boost_note}
        changed = {k: v for k, v in st.items() if k != "ts"} != self.state_cache
        if changed or self.tick % 10 == 0:
            self.state_cache = {k: v for k, v in st.items() if k != "ts"}
            core.write_json(core.AGENT_STATE, st)

    # ---- self-maintenance (runs on a background thread) ----
    def network_jobs(self):
        if not self.net_busy.acquire(blocking=False):
            return
        try:
            now = time.time()
            core.ensure_theme_files()           # files an older build's updater didn't know to copy (1.5.1.3)
            if core.pending_reports() and now - self.last_upload > 50:   # a small POST: fine even mid-game
                self.last_upload = now
                sent, failed = core.upload_reports()
                if sent or failed:
                    log(f"error reports: {sent} sent, {failed} failed")
            up = self.cfg.get("updates", {})
            st = core.update_state()
            if (up.get("auto_update") and not self.game and not core.on_probation("agent")
                    and now - st.get("last_check", 0) > core.UPDATE_INTERVAL_S and self.updated_to is None):
                res = core.check_for_update()
                if res["available"]:
                    ok, msg = core.install_update(res["remote"], res.get("branch", "main"))
                    log(msg)
                    if not ok:
                        core.report_update_failure(msg)
                    if ok:
                        self.updated_to = res["remote"]
                        add_alert(f"updated-{res['remote']}", f"{msg}. Restart the app to see what's new.")
                        subprocess.Popen(["systemctl", "--user", "restart", "allyhub-agent.service"],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif res["error"]:
                    log(f"update check: {res['error']}")
            self.keep_current(now)
        except Exception:
            core.report_exception("agent-network")
        finally:
            self.net_busy.release()

    def safely(self, name: str, fn, *args):
        try:
            fn(*args)
        except Exception:
            log(f"{name} failed: {sys.exc_info()[1]!r}")
            core.report_exception(f"agent-{name}")

    def run(self):
        log(f"Ally Hub agent {core.VERSION} starting")
        if core.startup_check("agent") == "rolled_back":
            log("rolled back a bad update, restarting on the previous version")
            sys.exit(1)
        self.safely("boost", self.recover_boost)
        self.safely("lighting", core.migrate_chip_spiral)
        self.safely("lighting", core.migrate_color_spirals)
        self.safely("refresh", core.retire_lab)          # 1.5.1.1: a lab caught mid-run winds down once
        self.safely("privacy", core.secure_data_dir)
        self.safely("rescue", core.sync_testing_rescue)      # Testing: a way out that works without the app
        self.safely("menu", core.tidy_menu_entry)
        while not self.stopping:
            self.reload_config()
            if not self.cfg["agent"].get("enabled", True):
                self.safely("boost", self.end_boost, "agent stopped")
                log("agent disabled in config, exiting")
                return
            if self.control is None and self.tick % 30 == 0:
                self.safely("control", self.serve_control)
            battery = core.battery_info()
            if self.tick % 3 == 0:
                self.safely("game", self.update_game)
                self.safely("boost", self.update_boost, battery)
                self.safely("dock", self.update_dock)
            if self.cfg["agent"].get("guardian"):
                self.safely("guardian", self.guardian)
            if self.cfg["agent"].get("health_log"):
                self.safely("health", self.log_health, battery)
            if self.tick % 60 == 5:     # the kernel resets the charge limit at boot: put the owner's choice back once
                self.safely("battery", core.apply_charge_limit_once)
            self.safely("saves", self.save_backups, battery)
            self.safely("sleep", self.update_sleep, battery)
            self.safely("lighting", self.update_lighting, battery)
            self.safely("refresh", core.refresh_step)          # the higher-refresh trial and its undo
            self.safely("state", self.write_state)
            if not self.healthy and time.time() - self.started > core.HEALTHY_AFTER_S:
                self.healthy = True
                core.mark_healthy("agent")
            if self.tick % 60 == 5:
                threading.Thread(target=self.network_jobs, daemon=True).start()
            self.tick += 1
            self.wake.wait(1.0)
            self.wake.clear()


def main():
    agent = None

    def stop(_sig, _frame):
        # systemctl stop: finish the current step, leave the loop, then put Game Boost back (finally below).
        # A flag rather than an exception, so a stop can't land between changing the CPU and recording it.
        if agent is None:
            raise SystemExit(0)
        agent.stopping = True
        agent.wake.set()
    try:
        signal.signal(signal.SIGTERM, stop)
    except (ValueError, OSError):
        pass
    try:
        agent = Agent()
        agent.run()
    except KeyboardInterrupt:                     # not SystemExit: the rollback restart needs exit code 1
        pass
    except Exception:
        core.report_exception("agent")
        if core.on_probation("agent"):
            core.rollback("the background helper crashed right after updating")
        raise
    finally:
        if agent:
            agent.safely("boost", agent.end_boost, "agent stopped")


if __name__ == "__main__":
    sys.exit(main())
