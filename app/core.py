"""
Ally Hub core: everything that doesn't need Qt.
Shared by the GUI (gui.py) and the background agent (agent.py).
"""

import base64
import colorsys
import fcntl
import getpass
import hashlib
import json
import math
import os
import re
import shlex
import shutil
import socket
import stat
import subprocess
import tarfile
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

APP_NAME = "Ally Hub"

HOME = Path.home()
USER = os.environ.get("USER") or getpass.getuser()
APP_DIR = Path(__file__).resolve().parent
# Installed copies are flat (~/.local/share/allyhub). A repo checkout keeps the code in app/ and
# VERSION at the top, so look one level up too.
try:
    VERSION = next((p.read_text().strip() for p in (APP_DIR / "VERSION", APP_DIR.parent / "VERSION")
                    if p.exists()), "") or "0.0.0"
except OSError:
    VERSION = "0.0.0"
REPO_DEFAULT = "Ravenor907/AllyHub"
DATA_DIR = HOME / ".local/share/allyhub"
CONFIG_DIR = HOME / ".config/allyhub"
CONFIG_FILE = CONFIG_DIR / "config.json"
AGENT_STATE = DATA_DIR / "agent_state.json"
CONTROL_SOCK = DATA_DIR / "agent.sock"     # the Quick Access panel talks to the agent here
HEALTH_FILE = DATA_DIR / "health.jsonl"
LED_ROOT = Path("/sys/class/leds")
UDEV_LED_RULE = "/etc/udev/rules.d/99-allyhub-leds.rules"
UDEV_CHARGE_RULE = "/etc/udev/rules.d/99-allyhub-charge.rules"
AGENT_UNIT = HOME / ".config/systemd/user/allyhub-agent.service"
DECKY_PATH = HOME / "homebrew/services/PluginLoader"
DECKY_PLUGINS = HOME / "homebrew/plugins"
DECKY_STORE_API = "https://plugins.deckbrew.xyz/plugins"
DECKY_CDN = "https://cdn.tzatzikiweeb.moe/file/steam-deck-homebrew/versions/{}.zip"
STEAM_ROOT = HOME / ".local/share/Steam"
BOOT_VIDEO = HOME / ".steam/root/config/uioverrides/movies/deck_startup.webm"
SHADER_CACHE = STEAM_ROOT / "steamapps/shadercache"
BACKUP_DIR = HOME / "AllyHub-Backups"
EMUDECK_PATH = HOME / "Applications/EmuDeck.AppImage"
TAILSCALE_BIN = "/opt/tailscale/tailscale"

REFUSAL_PATTERNS = re.compile(
    r"not canon|not supported|unsupported|aborting|refus|did you mean", re.I)


# ==========================================================================
# Config (shared by GUI and agent; always read-modify-write)
# ==========================================================================

DEFAULT_CONFIG = {
    "theme": {"preset": "ROG Crimson", "accent": None, "accent2": None,
              "scale": 100, "controller_nav": "auto", "ui_scale": "auto",
              # Game Mode and Desktop Mode show the same size differently, so each remembers its own
              # (None = use the shared "scale"/"ui_scale" above, which older versions saved)
              "scale_gamemode": None, "scale_desktop": None, "ui_scale_gamemode": None, "ui_scale_desktop": None,
              "bars": "top",            # "sides": header/footer as icon columns
              "footer": False,          # bottom bar off by default (the owner's call)
              "advanced": False},       # Simple by default; Advanced shows the expert controls (1.4.0)
    "rgb": None,
    "agent": {
        "enabled": False, "battery_rings": False, "low_battery_flash": True,
        "game_colors": True, "dock_mode": False, "health_log": True,
        "guardian": True, "remote": False, "remote_port": 8787, "remote_pin": "",
        "save_backup": False, "save_backup_hours": 24,
        "save_backup_dir": str(BACKUP_DIR / "saves"),
    },
    # Save time machine (Tools > Saves): a snapshot of a game's saves each time it starts
    "saves": {"time_machine": False, "keep": 5},
    # First-run setup (Home > Setup). Existing installs count as set up; a fresh install sets done False.
    "setup": {"done": True, "checklist_hidden": False, "password_known": False},
    # Sleep guardian: USB devices the owner stopped from waking the handheld (sysfs DEVPATHs)
    "sleep": {"no_wake": []},
    "game_colors": {},
    "dock": {"lights": "off", "audio_hdmi": True},
    "wol": {"name": "Gaming PC", "mac": "", "broadcast": "255.255.255.255"},
    "guardian": {"decky_expected": False, "last_build": ""},
    # controller "huesync": Ally Hub leaves the rings alone and points to the HueSync Decky plugin
    # (the owner's call). "allyhub" turns on the Lighting studio and agent lighting.
    "lighting": {"effect": None, "fps": 20, "on_battery": "slow", "custom": {}, "controller": "huesync",
                 "chip_spiral": False},     # True once saved spirals were moved to the chip's spiral (1.3.4)
    # channel "stable" follows main; "testing" also follows the testing branch (the owner's test builds)
    "updates": {"repo": REPO_DEFAULT, "auto_update": True, "reporting": False, "channel": "stable"},
    # Tools > Performance. The tune-up itself lives in /etc, so only Game Boost's switch is here.
    "performance": {"boost": False},
}


def _merge(defaults: dict, data: dict) -> dict:
    out = {}
    for k, v in defaults.items():
        if isinstance(v, dict) and isinstance(data.get(k), dict):
            out[k] = _merge(v, data[k])
        elif k in data:
            out[k] = data[k]
        else:
            out[k] = json.loads(json.dumps(v))
    for k, v in data.items():
        if k not in out:
            out[k] = v
    return out


def load_config() -> dict:
    try:
        data = json.loads(CONFIG_FILE.read_text())
    except Exception:
        data = {}
    return _merge(DEFAULT_CONFIG, data)


_CONFIG_LOCK = threading.RLock()      # the agent writes config from several threads (panel, phone remote)


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with _CONFIG_LOCK:
        fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR, prefix=".config-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps(cfg, indent=2))
            os.replace(tmp, CONFIG_FILE)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


def update_config(fn: Callable[[dict], None]) -> dict:
    with _CONFIG_LOCK:
        cfg = load_config()
        fn(cfg)
        save_config(cfg)
        return cfg


def read_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


# ==========================================================================
# System helpers
# ==========================================================================

def run_quiet(cmd: list, timeout: int = 8) -> tuple:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip()
    except Exception:
        return 1, ""


def read_text(path, default: str = "") -> str:
    try:
        return Path(path).read_text().strip()
    except Exception:
        return default


def read_int(path, default=None):
    try:
        return int(read_text(path))
    except (TypeError, ValueError):
        return default


def os_release() -> dict:
    info = {}
    for line in read_text("/etc/os-release").splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            info[k] = v.strip('"')
    return info


def device_name() -> str:
    vendor = read_text("/sys/class/dmi/id/sys_vendor")
    product = read_text("/sys/class/dmi/id/product_name")
    return f"{vendor} {product}".strip() or "Unknown device"


def short_device_name(product: str = None) -> str:
    """"ROG Xbox Ally X" for people to read: no vendor, no model codes like RC73XA_RC73XA (device_name() keeps
    everything for reports)."""
    product = read_text("/sys/class/dmi/id/product_name") if product is None else product
    words = product.split()
    while len(words) > 1 and re.fullmatch(r"[A-Z0-9_-]*\d[A-Z0-9_-]*", words[-1]):
        words.pop()
    return " ".join(words) or device_name()


def in_game_mode() -> bool:
    return (os.environ.get("XDG_CURRENT_DESKTOP", "").lower() == "gamescope"
            or "GAMESCOPE_WAYLAND_DISPLAY" in os.environ)


def battery_dir() -> Optional[Path]:
    for bat in sorted(Path("/sys/class/power_supply").glob("BAT*")):
        return bat
    return None


def health_now() -> dict:
    """One health reading right now (the same fields the agent logs once a minute)."""
    b = battery_info()
    s = sensors()
    w = battery_power_w()
    return {"t": time.time(), "pct": read_int(b["path"] / "capacity") if b else None,
            "w": round(w, 2) if w else None,
            "cpu": round(s["cpu_temp"], 1) if s.get("cpu_temp") else None,
            "gpu": round(s["gpu_temp"], 1) if s.get("gpu_temp") else None}


def battery_info() -> dict:
    bat = battery_dir()
    if not bat:
        return {}
    info = {"path": bat, "capacity": read_text(bat / "capacity"),
            "status": read_text(bat / "status"), "cycles": read_text(bat / "cycle_count")}
    full = read_int(bat / "energy_full") or read_int(bat / "charge_full")
    design = read_int(bat / "energy_full_design") or read_int(bat / "charge_full_design")
    info["health"] = round(100 * full / design) if full and design else None
    limit_file = bat / "charge_control_end_threshold"
    info["limit_file"] = limit_file if limit_file.exists() else None
    info["limit"] = read_text(limit_file) if limit_file.exists() else ""
    return info


def battery_percent() -> str:
    b = battery_info()
    if not b.get("capacity"):
        return "n/a"
    s = f"{b['capacity']}%"
    if b.get("status"):
        s += f" ({b['status'].lower()})"
    return s


def sudo_password_set() -> Optional[bool]:
    """True when the user has a password, False only when passwd clearly says there is none (NP or locked),
    None when it can't tell. Callers block only on False, and the owner can override that ("I already have
    one", config setup.password_known), so a wrong answer here can never trap anyone in a loop."""
    rc, out = run_quiet(["passwd", "-S", USER])
    parts = out.split() if rc == 0 and out else []
    if len(parts) < 2 or parts[0] != USER:
        return None
    if parts[1] == "P":
        return True
    if parts[1] in ("NP", "L", "LK"):
        app_log("password", f"passwd -S says {parts[1]}")
        return False
    return None


def installed_flatpaks() -> set:
    if not shutil.which("flatpak"):
        return set()
    rc, out = run_quiet(["flatpak", "list", "--app", "--columns=application"], timeout=20)
    return set(out.split()) if rc == 0 else set()


def installed_decky_plugins() -> dict:
    """Map lowercase plugin name -> {dir, name, version}."""
    found = {}
    try:
        dirs = list(DECKY_PLUGINS.iterdir()) if DECKY_PLUGINS.exists() else []
    except OSError:
        return found
    for d in dirs:
        meta = read_json(d / "plugin.json", {}) or {}
        name = meta.get("name", d.name)
        version = (read_json(d / "package.json", {}) or {}).get("version", "")
        found[name.lower()] = {"dir": str(d), "name": name, "version": version}
    return found


def service_active(name: str, user: bool = False) -> bool:
    cmd = ["systemctl"] + (["--user"] if user else []) + ["is-active", name]
    return run_quiet(cmd)[1] == "active"


def sshd_active() -> bool:
    return service_active("sshd")


def local_ips() -> list:
    rc, out = run_quiet(["ip", "-4", "-o", "addr", "show", "scope", "global"])
    ips = re.findall(r"inet (\d+\.\d+\.\d+\.\d+)", out) if rc == 0 else []
    return [ip for ip in ips if not ip.startswith("100.")] + [ip for ip in ips if ip.startswith("100.")]


def flatpak_sd_access() -> bool:
    rc, out = run_quiet(["flatpak", "override", "--user", "--show"])
    return rc == 0 and "/run/media" in out


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{int(n)} B"
        n /= 1024
    return f"{n} B"


def disk_usage(path: str) -> str:
    try:
        u = shutil.disk_usage(path)
        return f"{human_size(u.free)} free of {human_size(u.total)}"
    except OSError:
        return "n/a"


def disk_free_ratio(path: str) -> float:
    try:
        u = shutil.disk_usage(path)
        return u.free / u.total
    except OSError:
        return 1.0


def sd_cards() -> list:
    base = Path("/run/media")
    out = []
    if base.exists():
        for p in base.rglob("*"):
            try:
                if p.is_dir() and os.path.ismount(p):
                    out.append(p)
            except OSError:
                pass
    return out


def dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                pass
    return total


def internet_ok(timeout: float = 2.0) -> bool:
    for host in (("1.1.1.1", 443), ("8.8.8.8", 53)):
        try:
            with socket.create_connection(host, timeout=timeout):
                return True
        except OSError:
            continue
    return False


# ==========================================================================
# Sensors (hwmon) and power
# ==========================================================================

def hwmon_by_name() -> dict:
    out = {}
    for h in Path("/sys/class/hwmon").glob("hwmon*"):
        out.setdefault(read_text(h / "name"), h)
    return out


def sensors() -> dict:
    hw = hwmon_by_name()
    data = {"cpu_temp": None, "gpu_temp": None, "fan_rpm": None, "gpu_power": None}
    if "k10temp" in hw:
        t = read_int(hw["k10temp"] / "temp1_input")
        data["cpu_temp"] = t / 1000 if t else None
    if "amdgpu" in hw:
        t = read_int(hw["amdgpu"] / "temp1_input")
        data["gpu_temp"] = t / 1000 if t else None
        p = read_int(hw["amdgpu"] / "power1_average") or read_int(hw["amdgpu"] / "power1_input")
        data["gpu_power"] = p / 1e6 if p else None
    for h in hw.values():
        rpm = read_int(h / "fan1_input")
        if rpm is not None:
            data["fan_rpm"] = rpm
            break
    return data


def battery_power_w() -> Optional[float]:
    bat = battery_dir()
    if not bat:
        return None
    p = read_int(bat / "power_now")
    if p:
        return p / 1e6
    cur, volt = read_int(bat / "current_now"), read_int(bat / "voltage_now")
    if cur and volt:
        return cur * volt / 1e12
    return None


def battery_energy_wh() -> tuple:
    """(energy_now, energy_full) in Wh if available."""
    bat = battery_dir()
    if not bat:
        return None, None
    now, full = read_int(bat / "energy_now"), read_int(bat / "energy_full")
    if now is None:
        cn, cf, v = read_int(bat / "charge_now"), read_int(bat / "charge_full"), \
            read_int(bat / "voltage_min_design") or read_int(bat / "voltage_now")
        if cn and cf and v:
            return cn * v / 1e12, cf * v / 1e12
        return None, None
    return now / 1e6, (full or 0) / 1e6


def time_left_text() -> str:
    b = battery_info()
    if b.get("status") == "Charging":
        return "charging"
    p = battery_power_w()
    now, _ = battery_energy_wh()
    if not p or not now or p < 0.5:
        return "n/a"
    hours = now / p
    return f"{int(hours)}h {int((hours % 1) * 60):02d}m"


# ==========================================================================
# Displays (dock detection) and audio
# ==========================================================================

def external_display_connected() -> bool:
    for conn in Path("/sys/class/drm").glob("card*-*"):
        name = conn.name.split("-", 1)[1]
        if name.startswith("eDP") or name.startswith("Writeback"):
            continue
        if read_text(conn / "status") == "connected":
            return True
    return False


DRM_ROOT = Path("/sys/class/drm")


def panel_resolution() -> Optional[tuple]:
    """(width, height) of the built-in screen, from the kernel's mode list."""
    for conn in sorted(DRM_ROOT.glob("card*-eDP-*")) + sorted(DRM_ROOT.glob("card*-DSI-*")):
        first = read_text(conn / "modes").splitlines()[:1]
        m = re.match(r"(\d+)x(\d+)", first[0]) if first else None
        if m:
            w, h = int(m.group(1)), int(m.group(2))
            return (max(w, h), min(w, h))     # some panels report portrait
    return None


def desktop_scale() -> float:
    """The scale Desktop Mode already gives every app (KDE's display scale), 1.0 if none. Read before Qt starts,
    from what Plasma exports or saves: QT_SCREEN_SCALE_FACTORS, kdeglobals, kwinoutputconfig.json, Xft.dpi."""
    found = []
    env = os.environ.get("QT_SCREEN_SCALE_FACTORS", "")
    found += [float(x) for x in re.findall(r"(?:^|[=;])\s*([0-9]+(?:\.[0-9]+)?)\s*(?=;|$)", env)]
    m = re.search(r"^\s*ScaleFactor\s*=\s*([0-9.]+)", read_text(HOME / ".config/kdeglobals"), re.M)
    if m:
        found.append(float(m.group(1)))
    try:
        outs = json.loads(read_text(HOME / ".config/kwinoutputconfig.json") or "[]")
        for block in outs if isinstance(outs, list) else []:
            for d in block.get("data") or [] if isinstance(block, dict) else []:
                if isinstance(d, dict) and isinstance(d.get("scale"), (int, float)):
                    found.append(float(d["scale"]))
    except (ValueError, AttributeError):
        pass
    if not found and os.environ.get("DISPLAY"):
        rc, out = run_quiet(["xrdb", "-query"], timeout=3)
        m = re.search(r"Xft\.dpi:\s*([0-9.]+)", out or "")
        if m:
            found.append(float(m.group(1)) / 96)
    found = [f for f in found if 0.5 <= f <= 4]
    return max(found) if found else 1.0


def auto_ui_scale(gamemode: bool = None) -> float:
    """Interface scale for the built-in screen: 1.5 on a 1080p 7-8 inch handheld. In Desktop Mode the desktop's
    own scaling already enlarges apps, so Auto only adds what's missing (otherwise it's scaled twice)."""
    res = panel_resolution()
    if not res:
        return 1.0
    factor = max(1.0, min(2.0, round(res[1] / 720 * 4) / 4))
    if gamemode is False:
        factor = max(1.0, round(factor / desktop_scale() * 4) / 4)
    return factor


def mode_key(gamemode: bool) -> str:
    return "gamemode" if gamemode else "desktop"


def theme_size(theme_cfg: dict, name: str, gamemode: bool):
    """This mode's own interface or text size, falling back to the shared one."""
    v = theme_cfg.get(f"{name}_{mode_key(gamemode)}")
    return theme_cfg.get(name, "auto" if name == "ui_scale" else 100) if v is None else v


def ui_scale(theme_cfg: dict, gamemode: bool = None) -> float:
    v = theme_cfg.get("ui_scale", "auto") if gamemode is None else theme_size(theme_cfg, "ui_scale", gamemode)
    if v == "auto":
        return auto_ui_scale(gamemode)
    try:
        return max(0.75, min(2.5, float(v)))
    except (TypeError, ValueError):
        return 1.0


def set_hdmi_audio(on: bool) -> None:
    rc, out = run_quiet(["pactl", "list", "short", "sinks"])
    if rc != 0:
        return
    sinks = [ln.split("\t")[1] for ln in out.splitlines() if "\t" in ln]
    hdmi = [s for s in sinks if "hdmi" in s.lower() or "displayport" in s.lower()]
    internal = [s for s in sinks if s not in hdmi]
    target = (hdmi if on else internal)[:1]
    if target:
        run_quiet(["pactl", "set-default-sink", target[0]])


# ==========================================================================
# Steam games (running game detection + names)
# ==========================================================================

def steam_library_dirs() -> list:
    libs = [STEAM_ROOT / "steamapps"]
    vdf = read_text(STEAM_ROOT / "steamapps/libraryfolders.vdf")
    for path in re.findall(r'"path"\s+"([^"]+)"', vdf):
        p = Path(path) / "steamapps"
        if p not in libs:
            libs.append(p)
    return libs


_shortcut_names = {}
_shortcut_mtime = 0.0


def _load_shortcuts():
    global _shortcut_names, _shortcut_mtime
    files = list((STEAM_ROOT / "userdata").glob("*/config/shortcuts.vdf"))
    mtime = max((f.stat().st_mtime for f in files), default=0)
    if mtime == _shortcut_mtime:
        return
    names = {}
    for f in files:
        try:
            data = f.read_bytes()
        except OSError:
            continue
        appids = [(m.start(), int.from_bytes(m.group(1), "little"))
                  for m in re.finditer(rb"\x02appid\x00(.{4})", data, re.S | re.I)]
        for m in re.finditer(rb"\x01appname\x00([^\x00]*)\x00", data, re.I):
            prior = [a for pos, a in appids if pos < m.start()]
            if prior:
                names[prior[-1]] = m.group(1).decode("utf-8", "replace")
    _shortcut_names, _shortcut_mtime = names, mtime


def game_name(appid: str) -> str:
    try:
        n = int(appid)
    except ValueError:
        return f"Game {appid}"
    if n > 0xFFFFFFFF:            # non-Steam shortcut game id
        _load_shortcuts()
        short = n >> 32
        return _shortcut_names.get(short, f"Non-Steam game {short}")
    for lib in steam_library_dirs():
        acf = read_text(lib / f"appmanifest_{n}.acf")
        m = re.search(r'"name"\s+"([^"]+)"', acf)
        if m:
            return m.group(1)
    return f"Steam game {n}"


def is_self_game(appid: Optional[str]) -> bool:
    """Ally Hub launched from the Steam library shows up as a "game"; it isn't one."""
    return bool(appid) and game_name(appid).strip().lower().startswith("ally hub")


class GameWatcher:
    """Finds the running Steam game by scanning process environments."""

    IGNORE = {"0", "769"}   # 769 = Steam's own client id

    def __init__(self):
        self.cache = {}     # pid -> appid or None
        self.uid = os.getuid()

    @staticmethod
    def _zombie(pid: int) -> bool:
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            return stat[stat.rindex(")") + 2] in "ZX"
        except (OSError, ValueError, IndexError):
            return True

    def scan(self) -> Optional[str]:
        live = {}
        try:
            pids = [int(p) for p in os.listdir("/proc") if p.isdigit()]
        except OSError:
            return None
        for pid in pids:
            if pid in self.cache:
                appid = self.cache[pid]
                if appid and self._zombie(pid):
                    appid = None            # exited but not reaped yet
                live[pid] = appid
                continue
            appid = None
            try:
                if os.stat(f"/proc/{pid}").st_uid == self.uid:
                    cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
                    if b"allyhub" not in cmd:
                        env = Path(f"/proc/{pid}/environ").read_bytes().split(b"\x00")
                        vals = {}
                        for kv in env:
                            if kv.startswith(b"SteamGameId=") or kv.startswith(b"SteamAppId="):
                                k, v = kv.split(b"=", 1)
                                vals[k] = v.decode()
                        appid = vals.get(b"SteamGameId") or vals.get(b"SteamAppId")
                        if appid in self.IGNORE:
                            appid = None
            except OSError:
                appid = None
            live[pid] = appid
        self.cache = live
        running = [(pid, a) for pid, a in live.items() if a]
        return max(running)[1] if running else None


# ==========================================================================
# RGB lighting
# ==========================================================================

@dataclass
class LedDevice:
    path: Path
    channels: list
    max_brightness: int
    enums: dict = field(default_factory=dict)
    channel_max: list = field(default_factory=list)   # from multi_max_intensity, if present

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def pretty(self) -> str:
        return self.name.split(":")[-1].replace("_", " ").title()


def find_leds() -> list:
    leds = []
    if not LED_ROOT.exists():
        return leds
    for d in sorted(LED_ROOT.iterdir()):
        if not (d / "multi_intensity").exists():
            continue
        channels = read_text(d / "multi_index").split() or ["red", "green", "blue"]
        maxb = read_int(d / "max_brightness", 255) or 255
        enums = {}
        for idx_file in d.glob("*_index"):
            attr = idx_file.name[: -len("_index")]
            if attr == "multi" or not (d / attr).exists():
                continue
            options = [o.strip("[]") for o in read_text(idx_file).split()]
            current = read_text(d / attr)
            if current.isdigit() and int(current) < len(options):
                current = options[int(current)]
            if options:
                enums[attr] = (options, current.strip("[]"))
        cmax = [int(x) for x in read_text(d / "multi_max_intensity").split() if x.isdigit()]
        leds.append(LedDevice(d, channels, maxb, enums, cmax))
    return leds


def hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb) -> str:
    return "#{:02x}{:02x}{:02x}".format(*[max(0, min(255, int(c))) for c in rgb])


# Hardware effect modes that let software set the color frame by frame. If the rings are left
# in a hardware mode such as rainbow or breathe (for example from Armoury Crate on Windows),
# the colors Ally Hub writes are ignored and the rings look like nothing happened.
STATIC_MODE_NAMES = ("monocolor", "static", "solid", "direct", "custom", "single", "fixed", "steady")
MODE_ATTRS = ("effect", "mode")


def static_mode(led: "LedDevice") -> dict:
    """{attr: option} that puts each hardware effect/mode attribute in its plain-color mode."""
    out = {}
    for attr, (options, _cur) in (led.enums or {}).items():
        if attr not in MODE_ATTRS:
            continue
        for want in STATIC_MODE_NAMES:
            hit = next((o for o in options if o.lower() == want), None)
            if hit:
                out[attr] = hit
                break
    return out


# Channel names that carry a whole color packed as 0xRRGGBB in one number. The ROG Xbox Ally X
# kernel driver exposes its rings as four zones named "rgb" (multi_index "rgb rgb rgb rgb").
PACKED_CHANNELS = ("rgb", "color", "colour")


# How a packed "rgb" channel wants its color. The guided light test finds the right one on the
# real hardware and saves it as config["lighting"]["encoding"].
#   packed     0xRRGGBB, ignore multi_max_intensity (default)
#   packed_bgr 0xBBGGRR
#   clamped    0xRRGGBB capped at multi_max_intensity (red/green come out blue on the owner's Ally X)
#   hex        0xRRGGBB written as hex text ("0xff0000"), the way HueSync writes these zones
LIGHT_ENCODINGS = ("packed", "packed_bgr", "clamped", "hex")
# Encodings the guided test tries (clamped is known to be wrong, kept only so saved configs still load)
TEST_ENCODINGS = ("hex", "packed", "packed_bgr")
# "hid" means: skip sysfs and talk to the controller's lighting chip directly (see "Direct HID")


def channel_value(ch: str, rgb: tuple, cmax: int = 0, encoding: str = None) -> int:
    r, g, b = (max(0, min(255, int(c))) for c in rgb)
    ch = ch.lower()
    if ch in PACKED_CHANNELS:
        enc = encoding if encoding in LIGHT_ENCODINGS else "packed"
        if enc == "packed_bgr":
            return (b << 16) | (g << 8) | r
        packed = (r << 16) | (g << 8) | b
        return min(packed, cmax) if (enc == "clamped" and cmax) else packed
    comp = {"red": r, "green": g, "blue": b}.get(ch, 0)
    if cmax and cmax != 255:
        comp = round(comp * cmax / 255)
    return comp


def led_intensities(led: LedDevice, rgb: tuple, encoding: str = None) -> str:
    cmax = led.channel_max if len(led.channel_max) == len(led.channels) else [0] * len(led.channels)
    out = []
    for ch, m in zip(led.channels, cmax):
        v = channel_value(ch, rgb, m, encoding)
        out.append(f"0x{v:06x}" if encoding == "hex" and ch.lower() in PACKED_CHANNELS else str(v))
    return " ".join(out)


def _numbers(text: str) -> Optional[list]:
    try:
        return [int(x, 0) for x in text.split()]
    except ValueError:
        return None


def has_packed_channels(leds: list) -> bool:
    return any(ch.lower() in PACKED_CHANNELS for led in leds for ch in led.channels)


def rgb_writes(led: LedDevice, rgb: tuple, brightness: int, enum_values: dict, encoding: str = None) -> list:
    intensities = led_intensities(led, rgb, encoding)
    writes = []
    # the user's own hardware choices win; otherwise force plain-color mode so writes show up
    values = dict(static_mode(led))
    values.update({k: v for k, v in (enum_values or {}).items() if v})
    for attr, value in values.items():
        if attr in led.enums:
            options = led.enums[attr][0]
            fallback = str(options.index(value)) if value in options else None
            writes.append((str(led.path / attr), value, fallback))
    writes.append((str(led.path / "multi_intensity"), intensities, None))
    writes.append((str(led.path / "brightness"), str(brightness), None))
    return writes


REQUIRED_LED_FILES = ("multi_intensity", "brightness")


def try_direct_writes(writes: list) -> bool:
    """Write sysfs values. Color and brightness must succeed; mode attributes are best effort
    (a udev rule may not cover them, and that alone shouldn't stop the color from changing)."""
    required = [p for p, _, _ in writes if Path(p).name in REQUIRED_LED_FILES]
    if not all(os.access(p, os.W_OK) for p in required):
        return False
    for path, value, fallback in writes:
        must = Path(path).name in REQUIRED_LED_FILES
        if not must and not os.access(path, os.W_OK):
            continue
        try:
            Path(path).write_text(value)
        except OSError:
            if fallback is not None:
                try:
                    Path(path).write_text(fallback)
                    continue
                except OSError:
                    pass
            if must:
                return False
    return True


def leds_writable(leds: list) -> bool:
    return bool(leds) and all(os.access(l.path / "multi_intensity", os.W_OK) for l in leds)


def apply_lighting(rgb: tuple, brightness: int, enums: dict = None, leds: list = None,
                   encoding: str = None) -> bool:
    leds = leds if leds is not None else find_leds()
    if not leds:
        return False
    writes = []
    for led in leds:
        b = min(brightness, led.max_brightness)
        w = rgb_writes(led, rgb, b, enums or {}, encoding)
        # mode attributes only need writing when they change (this runs up to 30 times a second)
        keep = []
        for path, value, fb in w:
            attr = Path(path).name
            if attr in led.enums and led.enums[attr][1] == value:
                continue
            keep.append((path, value, fb))
        writes += keep
    ok = try_direct_writes(writes)
    if ok:
        for led in leds:
            for path, value, _ in writes:
                attr = Path(path).name
                if Path(path).parent == led.path and attr in led.enums:
                    led.enums[attr] = (led.enums[attr][0], value)
    return ok


def write_test_color(leds: list, rgb: tuple, encoding: str) -> dict:
    """Write one test color straight to the LEDs and record exactly what happened."""
    out = {"wrote": [], "readback": [], "errors": []}
    for led in leds:
        for attr, value in static_mode(led).items():      # leave any hardware animation mode
            try:
                (led.path / attr).write_text(value)
            except OSError:
                pass
        vals = led_intensities(led, rgb, encoding)
        for name, value in (("brightness", str(led.max_brightness)), ("multi_intensity", vals)):
            try:
                (led.path / name).write_text(value)
            except OSError as e:
                out["errors"].append(f"{name}: {e.strerror or e}")
        out["wrote"].append(vals)
        out["readback"].append(read_text(led.path / "multi_intensity"))
    out["ok"] = not out["errors"]
    # did the kernel keep what we wrote? A capped driver turns every color into 255.
    pairs = [(_numbers(w), _numbers(r)) for w, r in zip(out["wrote"], out["readback"])]
    out["matches"] = None if any(w is None or r is None for w, r in pairs) else all(w == r for w, r in pairs)
    return out


# --------------------------------------------------------------------------
# Direct HID: the ASUS lighting protocol (same commands Armoury Crate and Handheld Daemon send)
# Needed on kernels that cap each zone of ally:rgb:joystick_rings at 255, which leaves sysfs
# able to show only blue. Effects map onto the chip's built-in modes and are sent
# once per change, never per frame: some of these commands are saved to the chip's memory.
#
# The sequence follows HueSync (github.com/honjow/HueSync, BSD-3-Clause, Copyright (c) 2024
# honjow), which drives the Xbox Ally X rings from Decky:
#   1. pick the hidraw interface whose HID usage is 0xFF31/0x0080 (not just any node)
#   2. turn off the Xbox Ally X "Dynamic Lighting" interface (usage 0x59/0x01): report [0x06, 0x01].
#      Left on, it overrides custom colors, and it comes back after sleep.
#   3. send "RGB enable" [0x5A, 0xD1, 0x09, 0x01, 0x02] before anything else. After Windows
#      turns the rings off, the chip ignores every color command until it gets this.
# --------------------------------------------------------------------------

DEV_ROOT = Path("/dev")
HIDRAW_ROOT = Path("/sys/class/hidraw")
HID_REPORT = 0x5A
HID_MODES = {"solid": 0x00, "pulse": 0x01, "rainbow": 0x02, "spiral": 0x03}
HID_SPEEDS = {"slow": 0xE1, "medium": 0xEB, "fast": 0xF5}
HID_ZONES = {"all": 0x00, "left_left": 0x01, "left_right": 0x02, "right_left": 0x03, "right_right": 0x04}
HID_PERMISSION_RULE = "/etc/udev/rules.d/70-allyhub-hid.rules"
RULES_MARKER = "# allyhub-lighting v2"
ASUS_VID = 0x0B05
HID_APP_LIGHTING = (0xFF31, 0x0080)      # the ASUS config interface that takes 0x5A packets
HID_APP_DYNAMIC = (0x0059, 0x0001)       # Windows Dynamic Lighting (LampArray)
HID_RGB_ENABLE = [HID_REPORT, 0xD1, 0x09, 0x01, 0x02]   # on while awake
HID_DYNAMIC_OFF = bytes([0x06, 0x01])


def _hid_buf(data: list) -> bytes:
    return bytes(data) + bytes(64 - len(data))


def hid_collections(desc: bytes) -> list:
    """Top-level application collections in a HID report descriptor, as (usage page, usage).
    The same numbers hidapi reports as usage_page/usage, which is what HueSync matches on."""
    out, page, usage, depth, i = [], 0, 0, 0, 0
    while i < len(desc):
        b = desc[i]
        if b == 0xFE:                                  # long item: skip it
            i += 3 + (desc[i + 1] if i + 1 < len(desc) else 0)
            continue
        size = (0, 1, 2, 4)[b & 3]
        data = int.from_bytes(desc[i + 1:i + 1 + size], "little")
        tag = b & 0xFC
        if tag == 0x04:                                # Usage Page (global)
            page = data
        elif tag == 0x08:                              # Usage (local)
            usage = data
        elif tag == 0xA0:                              # Collection
            if depth == 0 and data == 0x01:
                p, u = (usage >> 16, usage & 0xFFFF) if size == 4 or usage > 0xFFFF else (page, usage)
                out.append((p, u))
            depth += 1
        elif tag == 0xC0:                              # End Collection
            depth = max(0, depth - 1)
        if tag in (0x80, 0x90, 0xA0, 0xB0, 0xC0):      # main items clear the local usage
            usage = 0
        i += 1 + size
    return out


def hidraw_devices() -> list:
    """Every hidraw node with its USB ids and HID usages."""
    out = []
    if not HIDRAW_ROOT.exists():
        return out
    for d in sorted(HIDRAW_ROOT.glob("hidraw*")):
        m = re.search(r"HID_ID=([0-9A-Fa-f]+):([0-9A-Fa-f]+):([0-9A-Fa-f]+)", read_text(d / "device" / "uevent"))
        if not m:
            continue
        try:
            desc = (d / "device" / "report_descriptor").read_bytes()
        except OSError:
            desc = b""
        out.append({"node": DEV_ROOT / d.name, "vid": int(m.group(2), 16), "pid": int(m.group(3), 16),
                    "apps": hid_collections(desc)})
    return out


def led_hid_device(led: "LedDevice") -> Optional[Path]:
    """The HID device directory behind an LED (e.g. .../0003:0B05:1B4C.0005)."""
    try:
        p = (led.path / "device").resolve()
    except OSError:
        return None
    for _ in range(4):
        if (p / "hidraw").is_dir():
            return p
        p = p.parent
    return None


def led_hidraw(led: "LedDevice") -> Optional[Path]:
    dev = led_hid_device(led)
    if not dev:
        return None
    nodes = sorted((dev / "hidraw").glob("hidraw*"))
    return DEV_ROOT / nodes[0].name if nodes else None


def led_usb_ids(led: "LedDevice") -> Optional[tuple]:
    dev = led_hid_device(led)
    m = re.match(r"[0-9A-Fa-f]{4}:([0-9A-Fa-f]{4}):([0-9A-Fa-f]{4})\.", dev.name) if dev else None
    return (m.group(1).lower(), m.group(2).lower()) if m else None


def ally_hid_nodes(leds: list = None) -> dict:
    """{"lighting": node, "dynamic": node, "ids": {(vid, pid)}} for the controller behind the rings.
    Matches on HID usage like HueSync; falls back to the node behind the LED on older kernels."""
    leds = leds if leds is not None else find_leds()
    pids = {int(ids[1], 16) for ids in (led_usb_ids(l) for l in leds) if ids}
    asus = [d for d in hidraw_devices() if d["vid"] == ASUS_VID]
    if pids and any(d["pid"] in pids for d in asus):
        asus = [d for d in asus if d["pid"] in pids]
    light = next((d for d in asus if HID_APP_LIGHTING in d["apps"]), None)
    dyn = next((d for d in asus if HID_APP_DYNAMIC in d["apps"]), None)
    out = {"lighting": light["node"] if light else None, "dynamic": dyn["node"] if dyn else None,
           "ids": {(f"{d['vid']:04x}", f"{d['pid']:04x}") for d in (light, dyn) if d}}
    if out["lighting"] is None:
        out["lighting"] = next((n for n in (led_hidraw(l) for l in leds) if n), None)
    out["ids"] |= {ids for ids in (led_usb_ids(l) for l in leds) if ids}
    return out


def hid_available(leds: list = None) -> bool:
    return ally_hid_nodes(leds)["lighting"] is not None


def hid_writable(leds: list) -> bool:
    nodes = ally_hid_nodes(leds)
    want = [n for n in (nodes["lighting"], nodes["dynamic"]) if n]
    return bool(want) and all(os.access(n, os.W_OK) for n in want)


def lighting_access_ok(leds: list) -> bool:
    """Ally Hub can drive the rings without a password: sysfs, plus the lighting chip if there is one."""
    if not leds_writable(leds):
        return False
    return not hid_available(leds) or hid_writable(leds)


def hid_rules(leds: list) -> list:
    return sorted({f'KERNEL=="hidraw*", SUBSYSTEM=="hidraw", ATTRS{{idVendor}}=="{v}", '
                   f'ATTRS{{idProduct}}=="{p}", MODE:="0666", RUN+="/bin/chmod 0666 /dev/%k"'
                   for v, p in ally_hid_nodes(leds)["ids"]})


def _file_access(p: Path) -> str:
    try:
        st = os.stat(p)
    except OSError as e:
        return f"{p}: missing ({e.strerror})"
    return (f"{p}: mode {stat.S_IMODE(st.st_mode):o} uid {st.st_uid} "
            f"{'writable' if os.access(p, os.W_OK) else 'NOT writable'}")


def lighting_access_details(leds: list = None) -> str:
    """Exactly which lighting file or device isn't writable, for reports when permission won't stick."""
    leds = leds if leds is not None else find_leds()
    lines = [f"user uid {os.getuid()}"]
    for led in leds:
        lines += [_file_access(led.path / f) for f in ("multi_intensity", "brightness")]
    nodes = ally_hid_nodes(leds)
    lines.append(f"lighting chip: {nodes['lighting']}  dynamic lighting: {nodes['dynamic']}  ids: {sorted(nodes['ids'])}")
    lines += [_file_access(n) for n in (nodes["lighting"], nodes["dynamic"]) if n]
    for h in hidraw_devices():
        if h["vid"] == ASUS_VID:
            lines.append(_file_access(h["node"]) + f" ({h['pid']:04x} {h['apps']})")
    for rule in (UDEV_LED_RULE, HID_PERMISSION_RULE):
        body = read_text(Path(rule))
        lines.append(f"{rule}: " + (body.replace(chr(10), " | ")[:400] if body else "missing"))
    for other in ("/dev/inputplumber", "/run/udev/rules.d"):
        p = Path(other)
        if p.is_dir():
            lines.append(f"{other}: " + ", ".join(sorted(x.name for x in p.iterdir())[:20]))
    lines.append(f"sysfs ok: {leds_writable(leds)}  chip found: {hid_available(leds)}  chip ok: {hid_writable(leds)}")
    return "\n".join(lines)


def hid_brightness_level(brightness: int) -> int:
    if brightness <= 0:
        return 0
    return 1 if brightness < 85 else 2 if brightness < 170 else 3


ZONE_NAMES = ("left_left", "left_right", "right_left", "right_right")

# Routes the guided test tries one after another ("Method 1, Method 2, ..."). On the owner's Ally X the
# chip packets can arrive without errors while the rings stay blue: the kernel's own LED driver
# probably re-sends its capped (blue) value over ours. Each route varies one suspect.
#   kernel_off  switch the rings off through sysfs first, so the kernel driver has nothing to re-send
#   init        send the "ASUS Tech.Inc." handshake (HueSync only does this on a full reset)
#   each        set the four zones one by one (HueSync's custom-color path) instead of zone "all"
#   feature     send as HID feature reports instead of output reports
HID_METHODS = {
    "m1": {"name": "Chip only, kernel lights off", "kernel_off": True, "init": False, "each": False, "feature": False},
    "m2": {"name": "Chip only, zone by zone", "kernel_off": True, "init": False, "each": True, "feature": False},
    "m3": {"name": "Full handshake", "kernel_off": True, "init": True, "each": True, "feature": False},
    "m4": {"name": "Feature reports", "kernel_off": True, "init": True, "each": True, "feature": True},
    "m5": {"name": "Kernel lights left on", "kernel_off": False, "init": True, "each": False, "feature": False},
    # m2-m4 can get red right, then the next color sticks or comes out mixed (left and right
    # different). Partial updates point at packets sent too fast, and at switching the kernel's lights
    # off before EVERY color, which makes its driver send its own packets at the same moment.
    #   kernel_off "once"  only on the first send of a session, then wait `settle` seconds
    #   commit "first"     set+apply (0xB5/0xB4) only on the first send or a mode change, like
    #                      HueSync's custom-color path; later colors are just zone commands
    #   gap / repeat       seconds between packets / send the whole sequence again after 0.2 s
    "m6": {"name": "HueSync custom colors", "kernel_off": "once", "settle": 1.0, "init": False, "each": True,
           "feature": False, "commit": "first", "gap": 0.02},
    "m7": {"name": "Slow and steady", "kernel_off": "once", "settle": 1.0, "init": True, "each": True,
           "feature": False, "gap": 0.03, "repeat": 2},
    "m8": {"name": "Zone by zone, system lights untouched", "kernel_off": False, "init": False, "each": True,
           "feature": False, "commit": "first", "gap": 0.02},
}
DEFAULT_HID_METHOD = "m3"      # used when no method is saved
# what the guided test tries, in order (m1, m4 and m5 fail outright on the owner's Ally X)
TEST_HID_METHODS = ("m6", "m7", "m8", "m2", "m3")
_HID_SESSION = {}              # per method: kernel already switched off, last committed mode


def hid_reset_session():
    """Forget what was sent, so the next send does the full first-time sequence (new test, wake-up)."""
    _HID_SESSION.clear()
    _STREAM_CACHE.clear()


def hid_method(name: str = None) -> dict:
    return HID_METHODS.get(name or DEFAULT_HID_METHOD, HID_METHODS[DEFAULT_HID_METHOD])


def hid_packets(mode: str, color: tuple, color2: tuple = (0, 0, 0), speed: str = "medium",
                brightness: int = 255, zones: list = None, init: bool = True, each: bool = False,
                direction: int = 0) -> list:
    """64-byte packets that set the rings. zones: [(zone name, (r, g, b))] for per-zone solid colors."""
    def c(v):
        return [max(0, min(255, int(x))) for x in v]
    if each and not zones:
        zones = [(z, color) for z in ZONE_NAMES]
    packets = ([_hid_buf([HID_REPORT] + list(b"ASUS Tech.Inc."))] if init else []) + [
               _hid_buf(HID_RGB_ENABLE),
               _hid_buf([HID_REPORT, 0xBA, 0xC5, 0xC4, hid_brightness_level(brightness)])]
    for zone, col in (zones or [("all", color)]):
        r, g, b = c(col)
        r2, g2, b2 = c(color2)
        packets.append(_hid_buf([HID_REPORT, 0xB3, HID_ZONES[zone], HID_MODES[mode], r, g, b,
                                 HID_SPEEDS[speed] if mode != "solid" else 0x00, direction, 0x00, r2, g2, b2]))
    packets += [_hid_buf([HID_REPORT, 0xB5]), _hid_buf([HID_REPORT, 0xB4])]
    return packets


def _shape_packets(packets: list, m: dict, mode: str, key: str) -> list:
    """Apply a method's commit rule: drop set+apply when the mode was already committed."""
    if m.get("commit") != "first":
        return packets
    sess = _HID_SESSION.setdefault(key, {})
    if sess.get("mode") == mode:
        return [p for p in packets if p[1] not in (0xB5, 0xB4, 0xBA)]
    sess["mode"] = mode
    return packets


def _dynamic_off_for(m: dict, nodes: dict, key: str) -> Optional[str]:
    """Windows Dynamic Lighting off: once per session for the gentle methods (HueSync does it once)."""
    sess = _HID_SESSION.setdefault(key, {})
    gentle = m.get("commit") == "first" or m.get("kernel_off") == "once"
    if gentle and sess.get("dynamic_off"):
        return None
    sess["dynamic_off"] = True
    return hid_dynamic_lighting_off(nodes)


def _kernel_off_for(m: dict, leds: list, key: str) -> Optional[str]:
    k = m.get("kernel_off")
    if not k:
        return None
    sess = _HID_SESSION.setdefault(key, {})
    if k == "once" and sess.get("kernel_off"):
        return None
    note = kernel_lights_off(leds)
    sess["kernel_off"] = True
    if m.get("settle"):
        time.sleep(m["settle"])          # let the kernel driver finish its own packets first
    return note


def hid_effect_packets(effect: dict, brightness: int, init: bool = True, each: bool = False) -> list:
    """Map an Ally Hub effect onto the chip's built-in modes."""
    e = normalize_effect(effect)
    cols = [hex_to_rgb(x) for x in e["colors"]] or [(255, 255, 255)]
    speed = "slow" if e["speed"] < 0.7 else "medium" if e["speed"] < 1.5 else "fast"
    kind = e["type"]
    kw = {"init": init, "each": each}
    if kind == "spiral":
        # the chip's own spiral: rainbow only, speed and direction (hhd: 0x01 = turning left)
        return hid_packets("spiral", (0, 0, 0), speed=speed, brightness=brightness, init=init,
                           direction=0x01 if e.get("direction") == "ccw" else 0x00)
    if kind == "static":
        return hid_packets("solid", cols[0], brightness=brightness, **kw)
    if kind == "cycle":
        return hid_packets("rainbow", cols[0], speed=speed, brightness=brightness, **kw)
    if kind in ("breathe", "pulse"):
        return hid_packets("pulse", cols[0], (0, 0, 0), speed, brightness, **kw)
    if kind == "strobe":
        return hid_packets("pulse", cols[0], cols[1] if len(cols) > 1 else (0, 0, 0), "fast", brightness, **kw)
    # wave, candle and twinkle: the chip's two-color pulse is the closest match
    return hid_packets("pulse", cols[0], cols[1] if len(cols) > 1 else cols[0], speed, brightness, **kw)


HIDIOCSFEATURE_64 = (3 << 30) | (64 << 16) | (ord("H") << 8) | 0x06


def hid_send(node: Path, packets: list, feature: bool = False, gap: float = 0.004) -> tuple:
    """Send packets to a hidraw node. Returns (ok, error text)."""
    try:
        fd = os.open(str(node), os.O_RDWR)
    except OSError as e:
        return False, f"open {node.name}: {e.strerror or e}"
    try:
        for pk in packets:
            if feature:
                fcntl.ioctl(fd, HIDIOCSFEATURE_64, pk)
                time.sleep(gap)
                continue
            try:
                os.write(fd, pk)
            except OSError:
                fcntl.ioctl(fd, HIDIOCSFEATURE_64, pk)     # some firmware only takes feature reports
            time.sleep(gap)
        return True, ""
    except OSError as e:
        return False, f"write {node.name}: {e.strerror or e}"
    finally:
        os.close(fd)


def hid_dynamic_lighting_off(nodes: dict) -> str:
    """Best effort: stop Windows Dynamic Lighting from overriding our colors. Returns a note."""
    node = nodes.get("dynamic")
    if not node:
        return "no dynamic lighting interface"
    try:
        fd = os.open(str(node), os.O_RDWR)
        try:
            os.write(fd, HID_DYNAMIC_OFF)
        finally:
            os.close(fd)
        return f"dynamic lighting off ({node.name})"
    except OSError as e:
        return f"dynamic lighting {node.name}: {e.strerror or e}"


def kernel_lights_off(leds: list) -> str:
    """Turn the rings off through the kernel driver, so it has no color of its own to re-send."""
    done = []
    for led in leds or []:
        try:
            (led.path / "brightness").write_text("0")
            done.append(led.name)
        except OSError as e:
            return f"kernel off failed: {e.strerror or e}"
    return f"kernel lights off ({', '.join(done)})" if done else "no kernel LED"


def hid_streams(method: str = None) -> bool:
    """Methods that commit once and then take bare zone commands can be animated frame by frame,
    the way HueSync animates its custom effects (no chip-memory writes per frame)."""
    return hid_method(method).get("commit") == "first"


def migrate_chip_spiral() -> bool:
    """Once: saved spirals (current effect, saved effects, per-game colors) switch to the chip's own spiral, the
    new default. Afterwards a spiral set to Ally Hub's style stays that way. True when something changed."""
    if load_config()["lighting"].get("chip_spiral"):
        return False
    changed = []

    def fix(e):
        if isinstance(e, dict) and e.get("type") == "spiral" and e.get("engine") != "chip":
            e["engine"] = "chip"
            changed.append(1)

    def run(c):
        L = c["lighting"]
        fix(L.get("effect"))
        for e in (L.get("custom") or {}).values():
            fix(e)
        for e in (c.get("game_colors") or {}).values():
            fix(e)
        L["chip_spiral"] = True
    update_config(run)
    return bool(changed)


def uses_chip_effect(effect: dict) -> bool:
    e = normalize_effect(effect)
    return e["type"] == "spiral" and e.get("engine") == "chip"


STREAM_FPS_MAX = 30          # HueSync's rate for HID devices like the Ally
_STREAM_CACHE = {}


def _stream_nodes(leds: list) -> dict:
    """ally_hid_nodes, cached for a few seconds: frames go out up to 30 times a second."""
    ck = (tuple(str(l.path) for l in leds), str(HIDRAW_ROOT), str(DEV_ROOT))
    hit = _STREAM_CACHE.get(ck)
    if hit and time.monotonic() - hit[1] < 10 and hit[0]["lighting"] and hit[0]["lighting"].exists():
        return hit[0]
    nodes = ally_hid_nodes(leds)
    _STREAM_CACHE.clear()
    if nodes["lighting"]:
        _STREAM_CACHE[ck] = (nodes, time.monotonic())
    return nodes


def hid_zone_frame(zones: list, brightness: int, leds: list = None, method: str = None) -> bool:
    """Send one frame (four zone colors) to the chip. Brightness is folded into the colors, which
    dims smoothly instead of the chip's four brightness steps."""
    leds = leds if leds is not None else find_leds()
    m = hid_method(method)
    key = method or DEFAULT_HID_METHOD
    nodes = _stream_nodes(leds)
    if not nodes["lighting"]:
        return False
    _kernel_off_for(m, leds, key)
    _dynamic_off_for(m, nodes, key)
    k = max(0, min(255, int(brightness))) / 255
    scaled = [tuple(int(round(c * k)) for c in z) for z in zones]
    packets = hid_packets("solid", scaled[0], zones=list(zip(ZONE_NAMES, scaled)), init=m["init"])
    packets = _shape_packets(packets, m, "static:255", key)
    gap = m.get("stream_gap", 0.006)
    return hid_send(nodes["lighting"], packets, feature=m["feature"], gap=gap)[0]


def hid_apply_effect(effect: dict, brightness: int, leds: list = None, method: str = None) -> bool:
    leds = leds if leds is not None else find_leds()
    if hid_streams(method) and not uses_chip_effect(effect):
        # one still frame; the agent animates it (GUI previews, --apply-rgb, static colors)
        return hid_zone_frame(zone_frames(effect, 0.0), brightness, leds, method)
    m = hid_method(method)
    key = method or DEFAULT_HID_METHOD
    nodes = ally_hid_nodes(leds)
    if not nodes["lighting"]:
        return False
    _kernel_off_for(m, leds, key)
    _dynamic_off_for(m, nodes, key)
    e = normalize_effect(effect)
    packets = hid_effect_packets(e, brightness, init=m["init"], each=m["each"])
    packets = _shape_packets(packets, m, f"{e['type']}:{brightness}", key)
    return _send_method(nodes["lighting"], packets, m)[0]


def _send_method(node: Path, packets: list, m: dict) -> tuple:
    res = (True, "")
    for i in range(max(1, int(m.get("repeat", 1)))):
        if i:
            time.sleep(0.2)
        res = hid_send(node, packets, feature=m["feature"], gap=m.get("gap", 0.004))
        if not res[0]:
            break
    return res


def hid_test_color(leds: list, rgb: tuple, method: str = None) -> dict:
    out = {"wrote": [], "readback": [], "errors": []}
    m = hid_method(method)
    key = method or DEFAULT_HID_METHOD
    nodes = ally_hid_nodes(leds)
    if nodes["lighting"]:
        note = _kernel_off_for(m, leds, key)
        if note:
            out["readback"].append(note)
        note = _dynamic_off_for(m, nodes, key)
        if note:
            out["readback"].append(note)
        packets = _shape_packets(hid_packets("solid", rgb, init=m["init"], each=m["each"]), m, "static:255", key)
        ok, err = _send_method(nodes["lighting"], packets, m)
        out["wrote"].append(f"{nodes['lighting'].name} {method or DEFAULT_HID_METHOD} solid {rgb}")
        if not ok:
            out["errors"].append(err)
    else:
        out["errors"].append("no hidraw device for the lighting chip")
    out["ok"] = not out["errors"]
    return out


def sysfs_color_capped(leds: list) -> bool:
    """True when the kernel caps packed zones at 255, so sysfs can only make blue."""
    return any(ch.lower() in PACKED_CHANNELS and 0 < m <= 255
               for led in leds for ch, m in zip(led.channels, led.channel_max))


def lighting_diagnostics() -> str:
    """Plain-text inventory of every LED the kernel exposes, for bug reports and Ally Doctor."""
    lines = []
    if not LED_ROOT.exists():
        return "no /sys/class/leds"
    for d in sorted(LED_ROOT.iterdir()):
        files = {}
        for f in ("multi_index", "multi_intensity", "brightness", "max_brightness", "trigger"):
            if (d / f).exists():
                files[f] = read_text(d / f)[:120]
        extra = {}
        for x in sorted(d.iterdir())[:30]:
            if x.is_file() and x.name not in files and x.name != "uevent":
                extra[x.name] = read_text(x)[:120] if os.access(x, os.R_OK) else "(unreadable)"
        w = "writable" if os.access(d / "multi_intensity", os.W_OK) else "read-only"
        if "multi_intensity" in files:
            probe = LedDevice(d, [], 255)
            node = led_hidraw(probe)
            extra["_hidraw"] = (f"{node} ids={led_usb_ids(probe)} "
                                f"{'writable' if node and os.access(node, os.W_OK) else 'not writable'}"
                                if node else "none found")
        lines.append(f"{d.name}: {files} {w if 'multi_intensity' in files else 'not multicolor'} "
                     f"other={extra}")
    # every ASUS hidraw interface and its HID usage, so the right one can be picked from a report
    for h in hidraw_devices():
        if h["vid"] == ASUS_VID:
            apps = ", ".join(f"{p:04x}/{u:04x}" for p, u in h["apps"]) or "?"
            acc = "writable" if os.access(h["node"], os.W_OK) else "not writable"
            lines.append(f"hid {h['node'].name} {h['vid']:04x}:{h['pid']:04x} usages {apps} {acc}")
    return "\n".join(lines) or "no LEDs"


# ==========================================================================
# Lighting effects (rendered by the agent, previewed by the GUI)
# ==========================================================================

EFFECT_TYPES = {
    #           display name     colors (min, max)  extra setting label
    "static":  {"name": "Static",       "colors": (1, 1), "param": None},
    "breathe": {"name": "Breathe",      "colors": (1, 1), "param": "Lowest brightness"},
    "pulse":   {"name": "Heartbeat",    "colors": (1, 1), "param": None},
    "cycle":   {"name": "Color cycle",  "colors": (0, 0), "param": "Color strength"},
    "wave":    {"name": "Wave",         "colors": (2, 4), "param": None},
    "strobe":  {"name": "Strobe",       "colors": (1, 2), "param": None},
    "flicker": {"name": "Candle",       "colors": (1, 2), "param": "Flicker strength"},
    "twinkle": {"name": "Twinkle",      "colors": (2, 2), "param": "Sparkle amount"},
    "spiral":  {"name": "Spiral",       "colors": (0, 4), "param": "Color spread"},
}
EFFECT_DEFAULT_PARAM = {"breathe": 0.12, "cycle": 1.0, "flicker": 0.55, "twinkle": 0.45, "spiral": 0.75}
# Spiral-only settings (other effect types never carry these keys, so saved effects stay as they were)
SPIRAL_OPTIONS = {
    "direction": (("cw", "Clockwise"), ("ccw", "Counter-clockwise")),
    "layout": (("linked", "Flows across both sticks"), ("mirror", "Sticks mirror each other"),
               ("same", "Both sticks match")),
    # chip first and default (the owner, 1.3.4: the streamed spiral looks choppy, the chip's own is smooth)
    "engine": (("chip", "Built-in chip spiral (smoothest)"), ("smooth", "Ally Hub (your colors)")),
}
SPIRAL_DEFAULTS = {"direction": "cw", "layout": "linked", "engine": "chip", "rainbow": True}
# The rings have four lighting zones: the left and right half of each stick (ASUS zone order)
ZONE_POS = ((0, 0), (0, 1), (1, 0), (1, 1))     # (stick, half) for left_left, left_right, right_left, right_right
DEFAULT_COLORS = ["#e11d48", "#8b5cf6", "#06b6d4", "#22c55e"]

PRESETS = {
    "ROG Pulse":  {"type": "breathe", "colors": ["#ff0033"], "speed": 1.0, "param": 0.08},
    "Xbox Glow":  {"type": "breathe", "colors": ["#22c55e"], "speed": 0.6, "param": 0.3},
    "Rainbow":    {"type": "cycle", "colors": [], "speed": 1.0, "param": 1.0},
    "Aurora":     {"type": "wave", "colors": ["#22c55e", "#14b8a6", "#6366f1", "#a855f7"], "speed": 0.55},
    "Synthwave":  {"type": "wave", "colors": ["#ff2a6d", "#05d9e8"], "speed": 0.8},
    "Ocean":      {"type": "wave", "colors": ["#0057ff", "#00d5ff", "#0033aa"], "speed": 0.35},
    "Sakura":     {"type": "wave", "colors": ["#ff5fa2", "#ffd6e7"], "speed": 0.45},
    "Ember":      {"type": "flicker", "colors": ["#ff5a00", "#ff1a00"], "speed": 1.0, "param": 0.6},
    "Heartbeat":  {"type": "pulse", "colors": ["#ff0022"], "speed": 1.0},
    "Starlight":  {"type": "twinkle", "colors": ["#2b1d8f", "#ffffff"], "speed": 1.0, "param": 0.5},
    "RGB Spiral": {"type": "spiral", "colors": [], "speed": 1.0, "param": 0.75, "rainbow": True,
                   "direction": "cw", "layout": "linked", "engine": "chip"},
    "Neon Vortex": {"type": "spiral", "colors": ["#ff2a6d", "#05d9e8", "#a855f7"], "speed": 1.4,
                    "param": 1.0, "rainbow": False, "direction": "ccw", "layout": "mirror", "engine": "chip"},
}


def _valid_hex(c) -> bool:
    return isinstance(c, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", c) is not None


def normalize_effect(e) -> dict:
    """Fill in defaults and clamp values so any stored effect is safe to render."""
    e = dict(e or {})
    etype = e.get("type") if e.get("type") in EFFECT_TYPES else "static"
    lo, hi = EFFECT_TYPES[etype]["colors"]
    colors = [c.lower() for c in (e.get("colors") or []) if _valid_hex(c)][:hi]
    extra = {}
    if etype == "spiral":
        for k, opts in SPIRAL_OPTIONS.items():
            extra[k] = e.get(k) if e.get(k) in [o for o, _ in opts] else SPIRAL_DEFAULTS[k]
        extra["rainbow"] = bool(e.get("rainbow", SPIRAL_DEFAULTS["rainbow"]))
        if not extra["rainbow"]:
            lo = 2                                # a color spiral needs at least two colors
    while len(colors) < lo:
        colors.append(DEFAULT_COLORS[len(colors) % len(DEFAULT_COLORS)])
    try:
        speed = max(0.1, min(4.0, float(e.get("speed", 1.0))))
    except (TypeError, ValueError):
        speed = 1.0
    try:
        param = max(0.0, min(1.0, float(e.get("param", EFFECT_DEFAULT_PARAM.get(etype, 0.5)))))
    except (TypeError, ValueError):
        param = EFFECT_DEFAULT_PARAM.get(etype, 0.5)
    return {"type": etype, "colors": colors, "speed": speed, "param": param, **extra}


def is_animated(e: dict) -> bool:
    return normalize_effect(e)["type"] != "static"


def _hash01(i: int, seed: int) -> float:
    x = (i * 374761393 + seed * 668265263) & 0xFFFFFFFF
    x = ((x ^ (x >> 13)) * 1274126177) & 0xFFFFFFFF
    return (x ^ (x >> 16)) / 0xFFFFFFFF


def _noise(x: float, seed: int) -> float:
    i = math.floor(x)
    f = x - i
    f = f * f * (3 - 2 * f)
    return _hash01(i, seed) * (1 - f) + _hash01(i + 1, seed) * f


def _lerp(a: tuple, b: tuple, t: float) -> tuple:
    return tuple(a[k] + (b[k] - a[k]) * t for k in range(3))


def render_effect(e: dict, t: float) -> tuple:
    """Color and brightness factor of an effect at time t (seconds).
    Returns ((r, g, b) floats 0..255, factor 0..1)."""
    e = normalize_effect(e)
    kind, sp, p = e["type"], e["speed"], e["param"]
    cols = [hex_to_rgb(c) for c in e["colors"]]
    if kind == "static":
        return cols[0], 1.0
    if kind == "breathe":
        ph = (t * sp / 4.0) % 1.0
        return cols[0], p + (1 - p) * (0.5 - 0.5 * math.cos(2 * math.pi * ph))
    if kind == "pulse":
        ph = (t * sp / 1.2) % 1.0
        beat = max(math.exp(-((ph - 0.08) / 0.05) ** 2), 0.7 * math.exp(-((ph - 0.3) / 0.05) ** 2))
        return cols[0], 0.06 + 0.94 * beat
    if kind == "cycle":
        r, g, b = colorsys.hsv_to_rgb((t * sp * 0.08) % 1.0, max(0.05, p), 1.0)
        return (r * 255, g * 255, b * 255), 1.0
    if kind == "wave":
        n = len(cols)
        pos = (t * sp / 3.0) % n
        i = int(pos)
        f = pos - i
        f = f * f * (3 - 2 * f)
        return _lerp(cols[i], cols[(i + 1) % n], f), 1.0
    if kind == "strobe":
        rate = sp * 2.0
        idx = int(t * rate)
        on = (t * rate) % 1.0 < (0.5 if len(cols) == 1 else 0.85)
        return cols[idx % len(cols)], 1.0 if on else 0.0
    if kind == "flicker":
        n = 0.6 * _noise(t * 7 * sp, 1) + 0.4 * _noise(t * 19 * sp, 2)
        color = _lerp(cols[0], cols[-1], _noise(t * 1.5 * sp, 3))
        return color, (1 - p) + p * n
    if kind == "twinkle":
        slot_rate = 3.0 * sp
        k = math.floor(t * slot_rate)
        spike = 0.0
        if _hash01(k, 7) < 0.15 + 0.7 * p:
            spike = math.sin(math.pi * ((t * slot_rate) % 1.0)) ** 2
        return _lerp(cols[0], cols[1], spike), 0.75 + 0.25 * spike
    return cols[0], 1.0


def effect_frame(e: dict, t: float) -> tuple:
    """Integer RGB intensities for an LED at time t (brightness folded in)."""
    e = normalize_effect(e)
    if e["type"] == "spiral":
        return zone_frames(e, t)[0]
    color, f = render_effect(e, t)
    return tuple(max(0, min(255, int(round(c * f)))) for c in color)


def _spiral_color(e: dict, u: float) -> tuple:
    if e.get("rainbow") or e.get("engine") == "chip":         # the chip's spiral is rainbow only: preview it so
        r, g, b = colorsys.hsv_to_rgb(u % 1.0, 1.0, 1.0)
        return (r * 255, g * 255, b * 255)
    cols = [hex_to_rgb(c) for c in e["colors"]]
    x = (u % 1.0) * len(cols)
    i = int(x)
    f = x - i
    f = f * f * (3 - 2 * f)
    return _lerp(cols[i % len(cols)], cols[(i + 1) % len(cols)], f)


def zone_frames(e: dict, t: float) -> list:
    """RGB for each of the four ring zones at time t. Only Spiral differs per zone; every other
    effect shows the same color on all zones, exactly like its preview."""
    e = normalize_effect(e)
    if e["type"] != "spiral":
        return [effect_frame(e, t)] * 4
    turn = 1 if e["direction"] == "cw" else -1
    phase = t * e["speed"] * 0.18     # the owner: 0.35 spun too fast on the rings
    out = []
    for stick, half in ZONE_POS:
        d, pos = turn, half / 2
        if e["layout"] == "linked" or e["engine"] == "chip":     # the chip ignores the stick layout
            pos = (stick * 2 + half) / 4
        elif e["layout"] == "mirror" and stick == 1:
            d, pos = -turn, (1 - half) / 2
        c = _spiral_color(e, d * phase + pos * e["param"])
        out.append(tuple(max(0, min(255, int(round(v)))) for v in c))
    return out


def effect_label(e: dict) -> str:
    e = normalize_effect(e)
    for name, p in PRESETS.items():
        if normalize_effect(p) == e:
            return name
    return EFFECT_TYPES[e["type"]]["name"]


def lookup_effect(ref, cfg: dict = None) -> Optional[dict]:
    """Resolve '#rrggbb', 'preset:Name' or an effect dict to an effect."""
    if isinstance(ref, dict):
        return normalize_effect(ref)
    if _valid_hex(ref):
        return normalize_effect({"type": "static", "colors": [ref]})
    if isinstance(ref, str) and ref.startswith("preset:"):
        name = ref[7:]
        custom = ((cfg or load_config()).get("lighting") or {}).get("custom") or {}
        if name in PRESETS:
            return normalize_effect(PRESETS[name])
        if name in custom:
            return normalize_effect(custom[name])
    return None


def base_effect(cfg: dict) -> Optional[dict]:
    """The user's chosen lighting: an effect, or their static color."""
    eff = (cfg.get("lighting") or {}).get("effect")
    if eff:
        return normalize_effect(eff)
    rgb = cfg.get("rgb")
    if rgb:
        return normalize_effect({"type": "static", "colors": [rgb_to_hex(rgb.get("rgb", (225, 29, 72)))]})
    return None


def lighting_shelved(cfg: dict = None) -> bool:
    """True when ring lighting is left to HueSync and Ally Hub must not touch the LEDs."""
    return ((cfg or load_config()).get("lighting") or {}).get("controller", "huesync") != "allyhub"


def led_permission_cmd(leds: list = None) -> str:
    """One password prompt that covers everything lighting needs: the sysfs ring files and,
    when the controller has one, the lighting chip's hidraw interfaces."""
    rule = ('ACTION=="add|change", SUBSYSTEM=="leds", KERNEL=="*:rgb:*", '
            'RUN+="/bin/sh -c \'chmod a+w /sys%p/brightness /sys%p/multi_intensity '
            '/sys%p/effect /sys%p/direction /sys%p/speed 2>/dev/null; true\'"')
    parts = [f"echo {shlex.quote(rule)} | tee {UDEV_LED_RULE} >/dev/null"]
    hid = hid_rules(leds) if leds is not None else []
    if hid:
        body = "\n".join([RULES_MARKER] + hid)
        parts.append(f"printf '%s\\n' {shlex.quote(body)} | tee {HID_PERMISSION_RULE} >/dev/null")
    parts += ["udevadm control --reload",
              "udevadm trigger --subsystem-match=leds --action=change",
              "udevadm trigger --subsystem-match=hidraw --action=change", "sleep 1"]
    # also open them up right now, so it works this session even if udev is slow or overridden
    now = []
    for led in leds or []:
        now += [str(led.path / f) for f in ("brightness", "multi_intensity", "effect", "mode")
                if (led.path / f).exists()]
    if now:
        parts.append("{ chmod a+w " + " ".join(shlex.quote(x) for x in now) + " 2>/dev/null; true; }")
    if leds is not None:
        nodes = ally_hid_nodes(leds)
        hid_now = [str(n) for n in (nodes["lighting"], nodes["dynamic"]) if n]
        if hid_now:
            parts.append("{ chmod 0666 " + " ".join(shlex.quote(x) for x in hid_now) + " 2>/dev/null; true; }")
    return ("sudo sh -c " + shlex.quote(" && ".join(parts)) +
            " && echo 'Lighting is now allowed without a password.'")


def battery_color(pct: int) -> tuple:
    """Red at 0%, yellow at 50%, green at 100%."""
    pct = max(0, min(100, pct))
    if pct < 50:
        return (255, int(255 * pct / 50), 0)
    return (int(255 * (100 - pct) / 50), 255, 0)


# ==========================================================================
# Wake-on-LAN
# ==========================================================================

def normalize_mac(mac: str) -> Optional[str]:
    hexes = re.sub(r"[^0-9a-fA-F]", "", mac or "")
    return hexes.lower() if len(hexes) == 12 else None


def send_wol(mac: str, broadcast: str = "255.255.255.255") -> bool:
    m = normalize_mac(mac)
    if not m:
        return False
    packet = b"\xff" * 6 + bytes.fromhex(m) * 16
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            for port in (9, 7):
                s.sendto(packet, (broadcast or "255.255.255.255", port))
        return True
    except OSError:
        return False


# ==========================================================================
# Health log
# ==========================================================================

def read_health(since: float = 0) -> list:
    rows = []
    try:
        with open(HEALTH_FILE) as f:
            for line in f:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if r.get("t", 0) >= since:
                    rows.append(r)
    except OSError:
        pass
    return rows


def per_game_drain(rows: list) -> list:
    """[(appid, avg_watts, samples)] for rows logged on battery during a game."""
    acc = {}
    for r in rows:
        g, w = r.get("game"), r.get("w")
        if g and w and r.get("st") == "Discharging":
            s = acc.setdefault(g, [0.0, 0])
            s[0] += w
            s[1] += 1
    return sorted(((g, s[0] / s[1], s[1]) for g, s in acc.items() if s[1] >= 3),
                  key=lambda x: -x[1])


# ==========================================================================
# Themes
# ==========================================================================

THEMES = {
    "ROG Crimson": dict(bg="#0e1016", side="#13151d", surface="#171a24", surface2="#232838",
                        border="#2e3448", text="#e7e9f0", muted="#8a91a6",
                        accent="#e11d48", accent2="#8b5cf6",
                        hero=("#3b0a1e", "#2a0f4a", "#0f1a3a"), on_accent="#ffffff"),
    "Xbox Green": dict(bg="#0a0f0b", side="#0f1510", surface="#141c15", surface2="#1d2a1f",
                       border="#2a3b2c", text="#e8f0e9", muted="#8aa18f",
                       accent="#107c10", accent2="#5dc21e",
                       hero=("#0b3d0b", "#14361a", "#0b1f14"), on_accent="#ffffff"),
    "Midnight Blue": dict(bg="#0a0f1e", side="#0e1427", surface="#131a30", surface2="#1c2542",
                          border="#2a3557", text="#e6ebf7", muted="#8792b3",
                          accent="#3b82f6", accent2="#06b6d4",
                          hero=("#0f2350", "#14305e", "#0a3a4a"), on_accent="#ffffff"),
    "Synthwave": dict(bg="#120b1f", side="#170e28", surface="#1d1232", surface2="#2a1a47",
                      border="#3d2763", text="#f6e9ff", muted="#a68cc7",
                      accent="#ff2a6d", accent2="#05d9e8",
                      hero=("#4a0d3a", "#2d1060", "#0b3b5c"), on_accent="#ffffff"),
    "Sunset": dict(bg="#140d0c", side="#1a1110", surface="#211614", surface2="#2f201c",
                   border="#45302a", text="#fbeee8", muted="#b39187",
                   accent="#f97316", accent2="#ec4899",
                   hero=("#5a1e08", "#4a1131", "#2a0f2a"), on_accent="#ffffff"),
    "OLED Black": dict(bg="#000000", side="#050505", surface="#0b0b0d", surface2="#16161a",
                       border="#24242a", text="#f2f2f5", muted="#86868f",
                       accent="#f2f2f5", accent2="#7c7c88",
                       hero=("#121214", "#0a0a0c", "#000000"), on_accent="#000000"),
    "Matrix": dict(bg="#020a04", side="#041007", surface="#07160b", surface2="#0c2213",
                   border="#14361e", text="#d6ffe0", muted="#6fae80",
                   accent="#22c55e", accent2="#84cc16",
                   hero=("#063314", "#0a2a10", "#021a08"), on_accent="#02140a"),
    "Frost Light": dict(bg="#f3f4f8", side="#e9ebf2", surface="#ffffff", surface2="#eceef5",
                        border="#d5d9e5", text="#151826", muted="#5d6479",
                        accent="#6366f1", accent2="#ec4899",
                        hero=("#e0e3ff", "#f3e1f5", "#dff1ff"), on_accent="#ffffff"),
}


def theme_palette(theme_cfg: dict) -> dict:
    pal = dict(THEMES.get(theme_cfg.get("preset"), THEMES["ROG Crimson"]))
    if theme_cfg.get("accent"):
        pal["accent"] = theme_cfg["accent"]
    if theme_cfg.get("accent2"):
        pal["accent2"] = theme_cfg["accent2"]
    pal["light"] = theme_cfg.get("preset") == "Frost Light"
    return pal


# ==========================================================================
# Catalog
# ==========================================================================

@dataclass
class Item:
    id: str
    name: str
    category: str
    desc: str
    monogram: str
    color: str
    install: str
    check: Callable[[dict], bool]
    uninstall: Optional[str] = None
    open_cmd: Optional[str] = None
    warn: str = ""
    requires: tuple = ()
    recommended: bool = False
    kind: str = "install"
    decky_names: tuple = ()


def flatpak_install_cmd(app_id: str) -> str:
    return ("flatpak remote-add --user --if-not-exists flathub "
            "https://dl.flathub.org/repo/flathub.flatpakrepo && "
            f"flatpak install --user -y --noninteractive flathub {app_id}")


def flatpak_item(app_id, name, category, desc, monogram, color, recommended=False, warn="") -> Item:
    return Item(
        id=app_id, name=name, category=category, desc=desc, monogram=monogram, color=color,
        install=flatpak_install_cmd(app_id),
        uninstall=f"flatpak uninstall -y --noninteractive {app_id} || "
                  f"flatpak uninstall --user -y --noninteractive {app_id}",
        open_cmd=f"flatpak run {app_id}",
        check=lambda s, a=app_id: a in s["flatpaks"],
        recommended=recommended, warn=warn,
    )


def decky_match(names: tuple, state: dict) -> list:
    dirs = []
    for key, info in state.get("decky", {}).items():
        base = Path(info["dir"]).name.lower()
        if any(n in key or n in base for n in names):
            dirs.append(info["dir"])
    return dirs


def fetch_run(url: str, shell: str = "bash") -> str:
    """Download an installer script, then run it the way `curl url | sh` does on SteamOS (sh is bash there):
    $0 stays the shell and stdin is the script, so Decky's `exec sudo "$0"` still works. The difference: a
    failed or cut-off download is never run (-f, and nothing runs until curl finished)."""
    return (f"( t=$(mktemp) && trap 'rm -f \"$t\"' EXIT && curl -fsSL {shlex.quote(url)} -o \"$t\" "
            f"&& {shell} < \"$t\" )")


def github_decky_install_cmd(repo: str, asset: str, plugin_names: tuple) -> str:
    """Install a Decky plugin the way Bazzite's ujust recipes do: the newest stable GitHub release
    (releases/latest never points at a pre-release). Any older copy, including a pre-release saved under
    another folder name, is removed first, but only after the download worked. Plugin settings live in
    ~/homebrew/settings, so they're kept."""
    url = shlex.quote(f"https://github.com/{repo}/releases/latest/download/{asset}")
    names = "|".join(re.escape(n) for n in plugin_names)
    match = shlex.quote(f'"name"[[:space:]]*:[[:space:]]*"({names})"')
    return (
        'tmp=$(mktemp -d) && '
        f'curl -fL -o "$tmp/p.zip" {url} && '
        'python3 -m zipfile -e "$tmp/p.zip" "$tmp/out" && '
        'ls -d "$tmp/out"/*/ >/dev/null && '
        'sudo mkdir -p "$HOME/homebrew/plugins" && '
        '{ for d in "$HOME/homebrew/plugins"/*/; do '
        f'grep -qiE {match} "$d/plugin.json" 2>/dev/null && sudo rm -rf "$d"; done; true; }} && '
        'for d in "$tmp/out"/*/; do n=$(basename "$d"); '
        'sudo rm -rf "$HOME/homebrew/plugins/$n"; '
        'sudo cp -r "$d" "$HOME/homebrew/plugins/$n"; '
        'sudo chown -R "$USER:$USER" "$HOME/homebrew/plugins/$n"; done && '
        'sudo systemctl restart plugin_loader; rc=$?; rm -rf "$tmp"; exit $rc'
    )


# ---------- NonSteamLaunchers, driven from Ally Hub's own page ----------
# NSL's script installs launchers silently when given their names as arguments (its Decky plugin's method).
# A stand-in `zenity` turns its windows into Activity log lines and answers "no" to questions.
# NSL works out the Steam account ID from loginusers.vdf and can get it wrong, and then its NSLGameScanner
# (which adds the Steam shortcuts) exits with "shortcuts.vdf does not exist" every time.
# So Ally Hub fixes the ID in NSL's env_vars before scanning, runs the scanner itself, and if a
# shortcut still isn't there, adds it the same way the scanner does: SteamClient.Apps through Steam's local
# CEF debugger (127.0.0.1:8080, the port Decky Loader already opens).
NSL_SCRIPT_URL = "https://raw.githubusercontent.com/moraroy/NonSteamLaunchers-On-Steam-Deck/main/NonSteamLaunchers.sh"
COMPATDATA = STEAM_ROOT / "steamapps/compatdata"
NSL_SHARED = "NonSteamLaunchers"
NSL_PREFIX = COMPATDATA / NSL_SHARED / "pfx/drive_c"
NSL_SEPARATE = "SEPARATE APP IDS - CHECK THIS TO SEPARATE YOUR PREFIX"
NSL_USER_DIR = HOME / ".config/systemd/user"
NSL_ENV = NSL_USER_DIR / "env_vars"
NSL_SCANNER = NSL_USER_DIR / "NSLGameScanner.py"
NSL_LOG = DATA_DIR / "nonsteamlaunchers.log"
NSL_DOWNLOADS = HOME / "Downloads/NonSteamLaunchersInstallation"
SHORTCUT_APP_TYPE = 1073741824           # Steam's app_type for non-Steam shortcuts
STEAM_ID64_BASE = 76561197960265728
CEF_PORT = 8080

# Stores: name -> (exe inside drive_c, own-prefix folder when "separate" is used, extra args, NSL uninstall name)
NSL_STORES = {
    "Epic Games": ("Program Files/Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe",
                   "EpicGamesLauncher", "-opengl", "Epic Games"),
    "GOG Galaxy": ("Program Files (x86)/GOG Galaxy/GalaxyClient.exe", "GogGalaxyLauncher", "", "GOG Galaxy"),
    "Ubisoft Connect": ("Program Files (x86)/Ubisoft/Ubisoft Game Launcher/upc.exe", "UplayLauncher", "", "Uplay"),
    "Battle.net": ("Program Files (x86)/Battle.net/Battle.net Launcher.exe", "Battle.netLauncher", "", "Battle.net"),
    "EA App": ("Program Files/Electronic Arts/EA Desktop/EA Desktop/EALauncher.exe", "TheEAappLauncher", "",
               "EA App"),
    "Amazon Games": ("users/steamuser/AppData/Local/Amazon Games/App/Amazon Games.exe", "AmazonGamesLauncher", "",
                     "Amazon Games"),
    "Rockstar Games Launcher": ("Program Files/Rockstar Games/Launcher/Launcher.exe", "RockstarGamesLauncher", "",
                                "Rockstar Games Launcher"),
    "itch.io": ("users/steamuser/AppData/Local/itch/itch.exe", "itchioLauncher", "", "itch.io"),
    "Humble Games Collection": ("Program Files/Humble App/Humble App.exe", "HumbleGamesLauncher", "",
                                "Humble Games Collection"),
    "Legacy Games": ("Program Files/Legacy Games/Legacy Games Launcher/Legacy Games Launcher.exe",
                     "LegacyGamesLauncher", "", "Legacy Games"),
    "IndieGala": ("Program Files/IGClient/IGClient.exe", "IndieGalaLauncher", "", "IndieGala"),
    "Minecraft Launcher": ("Program Files (x86)/Minecraft Launcher/MinecraftLauncher.exe", "MinecraftLauncher", "",
                           "Minecraft Launcher"),
    "Playstation Plus": ("Program Files (x86)/PlayStationPlus/pspluslauncher.exe", "PlaystationPlusLauncher", "",
                         "Playstation Plus"),
    "HoYoPlay": ("Program Files/HoYoPlay/launcher.exe", "HoYoPlayLauncher", "", "HoYoPlay"),
    "Game Jolt Client": ("users/steamuser/AppData/Local/GameJoltClient/GameJoltClient.exe", "GameJoltLauncher", "",
                         "Game Jolt Client"),
}
# Web and cloud: opened in Chrome (Flatpak), exactly like NSL's own shortcuts
NSL_WEB = {
    "Xbox Game Pass": "https://www.xbox.com/play", "Better xCloud": "https://better-xcloud.github.io",
    "GeForce Now": "https://play.geforcenow.com", "Amazon Luna": "https://luna.amazon.com",
    "Boosteroid Cloud Gaming": "https://cloud.boosteroid.com", "Youtube": "https://www.youtube.com",
    "Netflix": "https://www.netflix.com", "Twitch": "https://www.twitch.tv", "Disney+": "https://www.disneyplus.com",
    "Amazon Prime Video": "https://www.amazon.com/primevideo", "Crunchyroll": "https://www.crunchyroll.com",
    "Plex": "https://app.plex.tv/desktop/#!", "Hulu": "https://www.hulu.com/welcome",
}
CHROME_OPTIONS = ("run --branch=stable --arch=x86_64 --command=/app/bin/chrome --file-forwarding "
                  "com.google.Chrome @@u @@ --window-size=1280,800 --force-device-scale-factor=1.00 "
                  "--device-scale-factor=1.00 --start-fullscreen --no-first-run --enable-features=OverlayScrollbar")
NSL_GROUPS = {
    "Game stores": [(n, v[0]) for n, v in NSL_STORES.items()],
    "Cloud gaming": [(n, "") for n in ("Xbox Game Pass", "Better xCloud", "GeForce Now", "Amazon Luna",
                                       "Boosteroid Cloud Gaming", "Moonlight Game Streaming")],
    "TV and video": [(n, "") for n in ("Youtube", "Netflix", "Twitch", "Disney+", "Amazon Prime Video",
                                       "Crunchyroll", "Plex", "Hulu")],
}
NSL_NAMES = {name for group in NSL_GROUPS.values() for name, _ in group}

# Bash stand-in for zenity, used only for these jobs: progress text -> log lines, questions -> "no".
NSL_ZENITY = r"""#!/bin/sh
mode=""; text=""
for a in "$@"; do
  case "$a" in
    --progress|--question|--info|--warning|--error|--list|--entry|--file-selection) mode="$a" ;;
    --text=*) text="${a#--text=}" ;;
  esac
done
case "$mode" in
  --progress) while IFS= read -r line; do case "$line" in "#"*) echo "${line#\# }" ;; esac; done; exit 0 ;;
  --info|--warning|--error) [ -n "$text" ] && echo "$text"; exit 0 ;;
  *) [ -n "$text" ] && echo "(skipped question: $text)"; exit 1 ;;
esac
"""


# ----- where things are -----

def nsl_exe(name: str) -> Optional[Path]:
    """The installed launcher's .exe (shared prefix first, then its own prefix), or None."""
    info = NSL_STORES.get(name)
    if not info:
        return None
    rel, own, _args, _u = info
    for drive in (NSL_PREFIX, COMPATDATA / own / "pfx/drive_c"):
        p = drive / rel
        if p.exists():
            return p
        if name == "EA App":                 # EA moves EALauncher.exe around between versions
            hits = list((drive / "Program Files/Electronic Arts").rglob("EALauncher.exe")) \
                if (drive / "Program Files/Electronic Arts").exists() else []
            if hits:
                return hits[0]
    return None


def nsl_installed(name: str) -> bool:
    return nsl_exe(name) is not None


def nsl_compatdata_for(exe: Path) -> Path:
    """compatdata/<prefix> that holds this exe."""
    parts = exe.parts
    i = parts.index("compatdata")
    return Path(*parts[:i + 2])


def steam_user_id3() -> Optional[str]:
    """The signed-in Steam account's userdata folder name. NSL's own guess can be wrong."""
    best, best_key = None, None
    for f in (STEAM_ROOT / "config/loginusers.vdf", HOME / ".steam/root/config/loginusers.vdf"):
        text = read_text(f)
        for sid, body in re.findall(r'"(\d{17})"\s*\{([^{}]*)\}', text):
            recent = 1 if re.search(r'"MostRecent"\s*"1"', body, re.I) else 0
            m = re.search(r'"Timestamp"\s*"(\d+)"', body, re.I)
            key = (recent, int(m.group(1)) if m else 0)
            id3 = str(int(sid) - STEAM_ID64_BASE)
            if (HOME / ".steam/root/userdata" / id3).exists() and (best_key is None or key > best_key):
                best, best_key = id3, key
        if best:
            return best
    # no usable loginusers.vdf: the userdata folder Steam touched last
    dirs = [d for d in (HOME / ".steam/root/userdata").glob("*") if d.name.isdigit() and d.name != "0"]
    dirs.sort(key=lambda d: max((p.stat().st_mtime for p in (d / "config").glob("*.vdf")), default=0),
              reverse=True)
    return dirs[0].name if dirs else None


def shortcuts_vdf(id3: str = None) -> Optional[Path]:
    id3 = id3 or steam_user_id3()
    return HOME / ".steam/root/userdata" / id3 / "config/shortcuts.vdf" if id3 else None


def steam_shortcut_names() -> set:
    """App names in every Steam user's non-Steam shortcuts (binary shortcuts.vdf, read loosely)."""
    names = set()
    for f in (HOME / ".steam/root/userdata").glob("*/config/shortcuts.vdf"):
        try:
            data = f.read_bytes()
        except OSError:
            continue
        for m in re.finditer(rb"\x01(?:appname|AppName)\x00([^\x00]*)\x00", data):
            names.add(m.group(1).decode("utf-8", "replace"))
    return names


# ----- shell pieces -----

def _nsl_prep_shell(id3: Optional[str]) -> str:
    """Give NSL's scanner the right Steam account and a shortcuts.vdf it won't wipe (it empties the file
    when it isn't executable). The real file is backed up first."""
    if not id3:
        return "echo 'Could not find your Steam account folder.'"
    vdf_path = shlex.quote(str(shortcuts_vdf(id3)))
    env = shlex.quote(str(NSL_ENV))
    backup = shlex.quote(str(DATA_DIR / "shortcuts.vdf.bak"))
    return (
        f'mkdir -p "$(dirname {vdf_path})" {shlex.quote(str(NSL_USER_DIR))} && touch {env} && '
        f'sed -i "/^export steamid3=/d" {env} && echo "export steamid3={id3}" >> {env} && '
        f'grep -q "^export logged_in_home=" {env} || echo "export logged_in_home={HOME}" >> {env}; '
        f'if [ -s {vdf_path} ]; then cp {vdf_path} {backup}; '
        f"else printf '\\000shortcuts\\000\\010\\010' > {vdf_path}; fi; chmod 755 {vdf_path}"
    )


def _shim_shell() -> str:
    return ('shim=$(mktemp -d) && '
            f"printf '%s' {shlex.quote(NSL_ZENITY)} > \"$shim/zenity\" && chmod +x \"$shim/zenity\" && "
            f'curl -fsSL {shlex.quote(NSL_SCRIPT_URL)} -o "$shim/nsl.sh"')


def _scan_shell() -> str:
    log = shlex.quote(str(NSL_LOG))
    return (
        'echo "Adding the new launchers to your Steam library..."; '
        'systemctl --user stop nslgamescanner.service 2>/dev/null; '
        f'if [ -f {shlex.quote(str(NSL_SCANNER))} ]; then '
        f'timeout 600 python3 {shlex.quote(str(NSL_SCANNER))} > "$shim/scan.log" 2>&1; '
        f'echo "scanner exit $?" >> "$shim/scan.log"; tail -n 60 "$shim/scan.log" | tee -a {log}; fi; '
        'systemctl --user start nslgamescanner.service 2>/dev/null; true'
    )


def nsl_install_cmd(names: list, separate: bool = False, id3: str = None) -> Optional[str]:
    """One job: run NonSteamLaunchers for the chosen launchers, fix its Steam account, then scan."""
    picked = [n for n in names if n in NSL_NAMES]
    if not picked:
        return None
    if any(n in NSL_WEB for n in picked):
        picked.append("Google Chrome")       # NSL builds web shortcuts only when a browser is chosen
    args = ([NSL_SEPARATE] if separate else []) + picked
    id3 = id3 if id3 is not None else steam_user_id3()
    log = shlex.quote(str(NSL_LOG))
    return (
        _shim_shell() + ' && ' + f'mkdir -p {shlex.quote(str(DATA_DIR))} && ' +
        f'{{ PATH="$shim:$PATH" bash "$shim/nsl.sh" ' + " ".join(shlex.quote(a) for a in args) +
        f' 2>&1; echo "nsl exit $?"; }} | tee {log}; '
        f'rc=$(grep "^nsl exit " {log} | tail -n1 | sed "s/^nsl exit //"); ' +
        _nsl_prep_shell(id3) + '; ' + _scan_shell() + '; '
        'rm -rf "$shim"; [ "${rc:-1}" = 0 ] && echo "Done."; exit "${rc:-1}"'
    )


def nsl_uninstall_cmd(names: list) -> Optional[str]:
    """Remove launchers with NSL's own uninstaller (program files and own prefix). Steam tiles are removed
    separately through Steam (cef_remove_shortcuts)."""
    stores = [NSL_STORES[n][3] for n in names if n in NSL_STORES]
    if not stores:
        return None
    args = " ".join(shlex.quote(f"Uninstall {u}") for u in stores)
    return (_shim_shell() + ' && ' + f'mkdir -p {shlex.quote(str(DATA_DIR))} && '
            f'{{ PATH="$shim:$PATH" bash "$shim/nsl.sh" {args} 2>&1; echo "nsl exit $?"; }} '
            f'| tee {shlex.quote(str(NSL_LOG))}; rm -rf "$shim"; echo "Uninstall finished."')


# ----- Steam's own API through its local debugger (what NSL's scanner and Decky use) -----

def _ws_send(sock, text: str):
    data = text.encode()
    head = bytearray([0x81])
    n = len(data)
    if n < 126:
        head.append(0x80 | n)
    elif n < 65536:
        head += bytes([0x80 | 126]) + n.to_bytes(2, "big")
    else:
        head += bytes([0x80 | 127]) + n.to_bytes(8, "big")
    mask = os.urandom(4)
    if n:                                   # whole-buffer XOR: art payloads are megabytes
        full = (mask * (n // 4 + 1))[:n]
        data = (int.from_bytes(data, "big") ^ int.from_bytes(full, "big")).to_bytes(n, "big")
    sock.sendall(bytes(head) + mask + data)


def _recv_exact(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def _ws_recv(sock) -> Optional[str]:
    parts = []
    while True:
        b1, b2 = _recv_exact(sock, 2)
        n = b2 & 0x7F
        if n == 126:
            n = int.from_bytes(_recv_exact(sock, 2), "big")
        elif n == 127:
            n = int.from_bytes(_recv_exact(sock, 8), "big")
        mask = _recv_exact(sock, 4) if b2 & 0x80 else None
        payload = _recv_exact(sock, n)
        if mask:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        op = b1 & 0x0F
        if op == 0x8:
            return None
        if op in (0x1, 0x0):
            parts.append(payload)
            if b1 & 0x80:
                return b"".join(parts).decode("utf-8", "replace")


def cef_eval(js: str, timeout: float = 20, port: int = None):
    """Run JavaScript in Steam's SharedJSContext and return its value. None when Steam's debugger is off."""
    port = port or CEF_PORT
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3) as r:
            targets = json.loads(r.read())
    except Exception:
        return None
    url = next((t.get("webSocketDebuggerUrl") for t in targets if t.get("title") == "SharedJSContext"), None)
    if not url:
        return None
    m = re.match(r"ws://([^/:]+):(\d+)(/.*)", url)
    if not m:
        return None
    try:
        with socket.create_connection((m.group(1), int(m.group(2))), timeout=timeout) as s:
            key = base64.b64encode(os.urandom(16)).decode()
            s.sendall((f"GET {m.group(3)} HTTP/1.1\r\nHost: {m.group(1)}:{m.group(2)}\r\nUpgrade: websocket\r\n"
                       f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
            resp = b""
            while b"\r\n\r\n" not in resp:
                chunk = s.recv(4096)
                if not chunk:
                    return None
                resp += chunk
            if b" 101" not in resp.split(b"\r\n", 1)[0]:
                return None
            _ws_send(s, json.dumps({"id": 1, "method": "Runtime.evaluate",
                                    "params": {"expression": js, "awaitPromise": True, "returnByValue": True}}))
            while True:
                msg = _ws_recv(s)
                if msg is None:
                    return None
                data = json.loads(msg)
                if data.get("id") == 1:
                    return ((data.get("result") or {}).get("result") or {}).get("value")
    except (OSError, ValueError, ConnectionError):
        return None


def cef_shortcut_names() -> Optional[set]:
    v = cef_eval("JSON.stringify((window.appStore?.allApps||[]).filter(a=>a?.app_type===%d)"
                 ".map(a=>a.display_name))" % SHORTCUT_APP_TYPE)
    try:
        return set(json.loads(v)) if v else None
    except ValueError:
        return None


def latest_ge_proton() -> str:
    tools = [p for p in custom_protons() if p.lower().startswith("ge-proton")]
    return sorted(tools, key=parse_version)[-1] if tools else "proton_experimental"


def nsl_shortcut_spec(name: str) -> Optional[dict]:
    """The Steam shortcut NSL would make for this launcher (same exe, start dir, launch options, Proton)."""
    if name in NSL_STORES:
        exe = nsl_exe(name)
        if not exe:
            return None
        args = NSL_STORES[name][2]
        return {"appname": name, "exe": f'"{exe}"' + (f" {args}" if args else ""),
                "StartDir": f'"{exe.parent}"',
                "LaunchOptions": f'STEAM_COMPAT_DATA_PATH="{nsl_compatdata_for(exe)}/" %command%',
                "CompatTool": latest_ge_proton()}
    if name in NSL_WEB:
        return {"appname": name, "exe": '"/usr/bin/flatpak"', "StartDir": '"/usr/bin"',
                "LaunchOptions": f"{CHROME_OPTIONS} {NSL_WEB[name]}", "CompatTool": ""}
    return None


CEF_ADD_JS = """(async () => {
  const specs = %s, done = [];
  const have = new Set((window.appStore?.allApps||[]).filter(a=>a?.app_type===%d).map(a=>a.display_name));
  for (const d of specs) {
    if (have.has(d.appname)) { done.push(d.appname); continue; }
    try {
      const id = await SteamClient.Apps.AddShortcut(d.appname, d.exe, d.StartDir, d.LaunchOptions);
      await SteamClient.Apps.SetShortcutName(id, d.appname);
      await SteamClient.Apps.SetShortcutExe(id, d.exe);
      await SteamClient.Apps.SetShortcutStartDir(id, d.StartDir);
      await SteamClient.Apps.SetAppLaunchOptions(id, d.LaunchOptions);
      if (d.CompatTool) {
        const tools = await SteamClient.Apps.GetAvailableCompatTools(id);
        const tool = tools.some(t => t.strToolName === d.CompatTool) ? d.CompatTool : 'proton_experimental';
        await SteamClient.Apps.SpecifyCompatTool(id, tool);
      }
      done.push(d.appname);
    } catch (e) { console.error('Ally Hub shortcut', d.appname, e); }
  }
  return JSON.stringify(done);
})()"""

CEF_REMOVE_JS = """(async () => {
  const names = new Set(%s), done = [];
  for (const a of (window.appStore?.allApps||[])) {
    if (a?.app_type === %d && names.has(a.display_name)) {
      try { await SteamClient.Apps.RemoveShortcut(a.appid); done.push(a.display_name); } catch (e) {}
    }
  }
  return JSON.stringify(done);
})()"""


def cef_add_shortcuts(names: list) -> Optional[list]:
    """Add the missing Steam tiles directly. Returns the names now in the library, or None if Steam's
    debugger isn't reachable."""
    specs = [s for s in (nsl_shortcut_spec(n) for n in names) if s]
    if not specs:
        return []
    v = cef_eval(CEF_ADD_JS % (json.dumps(specs), SHORTCUT_APP_TYPE), timeout=40)
    try:
        return json.loads(v) if v else None
    except ValueError:
        return None


def cef_remove_shortcuts(names: list) -> Optional[list]:
    v = cef_eval(CEF_REMOVE_JS % (json.dumps(list(names)), SHORTCUT_APP_TYPE), timeout=30)
    try:
        return json.loads(v) if v else None
    except ValueError:
        return None


# ----- Library art: covers, banners and icons for non-Steam tiles, made on the handheld -----
# No downloads. The icon comes out of the program's own .exe (its icon resources); the art is drawn as SVG
# here (stdlib) and turned into PNGs by the GUI's Qt. Steam gets it live through the same debugger
# connection as the shortcuts (SetCustomArtworkForApp / SetShortcutIcon); the grid-folder copies make it
# show after a Steam restart when that connection is off.

ART_DIR = DATA_DIR / "art"
_ART_LOCK = threading.Lock()
ART_MADE = DATA_DIR / "art_made.json"
# Steam's library asset types for SetCustomArtworkForApp, and the grid-folder file each one uses
ART_KINDS = {"portrait": (0, "{id}p.png", 600, 900), "hero": (1, "{id}_hero.png", 1920, 620),
             "logo": (2, "{id}_logo.png", 1200, 300), "wide": (3, "{id}.png", 920, 430)}
ART_GRID_EXTS = (".png", ".jpg", ".jpeg", ".webp")
ART_FALLBACK_COLOR = "#3b82f6"
ART_FONT = "Inter, Noto Sans, DejaVu Sans, sans-serif"


def steam_grid_dir(id3: str = None) -> Optional[Path]:
    id3 = id3 or steam_user_id3()
    return HOME / ".steam/root/userdata" / id3 / "config/grid" if id3 else None


def _vdf_shortcuts(data: bytes) -> list:
    """Loose reader for binary shortcuts.vdf: [{appid, name, exe, icon}] (appid as Steam's unsigned id)."""
    out = []
    starts = [m.start() for m in re.finditer(rb"\x02appid\x00", data, re.I)]
    for i, s in enumerate(starts):
        seg = data[s:starts[i + 1] if i + 1 < len(starts) else len(data)]
        if len(seg) < 11:
            continue
        ent = {"appid": int.from_bytes(seg[7:11], "little")}
        for key, field_name in ((rb"appname", "name"), (rb"exe", "exe"), (rb"icon", "icon"),
                                (rb"LaunchOptions", "options")):
            m = re.search(rb"\x01" + key + rb"\x00([^\x00]*)\x00", seg, re.I)
            ent[field_name] = m.group(1).decode("utf-8", "replace") if m else ""
        m = re.search(rb"\x02LastPlayTime\x00(.{4})", seg, re.S | re.I)
        ent["last"] = int.from_bytes(m.group(1), "little") if m else 0
        if ent["name"]:
            out.append(ent)
    return out


def steam_shortcuts() -> list:
    """Non-Steam tiles: Steam's live list when its debugger is on (exact ids), merged with shortcuts.vdf."""
    f = shortcuts_vdf()
    try:
        disk = _vdf_shortcuts(f.read_bytes()) if f and f.exists() else []
    except OSError:
        disk = []
    v = cef_eval("JSON.stringify((window.appStore?.allApps||[]).filter(a=>a?.app_type===%d)"
                 ".map(a=>({appid:a.appid,name:a.display_name})))" % SHORTCUT_APP_TYPE)
    try:
        live = json.loads(v) if v else None
    except ValueError:
        live = None
    live = [a for a in live if isinstance(a, dict)] if isinstance(live, list) else None
    if not live:
        return disk
    by_id = {d["appid"]: d for d in disk}
    by_name = {d["name"].lower(): d for d in disk}
    out = []
    for a in live:
        d = by_id.get(a.get("appid")) or by_name.get(str(a.get("name", "")).lower()) or {}
        out.append({"appid": int(a.get("appid") or 0), "name": a.get("name") or d.get("name", ""),
                    "exe": d.get("exe", ""), "icon": d.get("icon", "")})
    return [s for s in out if s["appid"] and s["name"]]


def _grid_files(appid: int, kind: str, grid: Path) -> list:
    stem = ART_KINDS[kind][1].format(id=appid)[:-4]
    return [grid / f"{stem}{e}" for e in ART_GRID_EXTS if (grid / f"{stem}{e}").exists()] if grid else []


def has_grid_art(appid: int, grid: Path = None) -> bool:
    return bool(_grid_files(appid, "portrait", grid or steam_grid_dir()))


def _sha(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def art_is_ours(appid: int, kind: str, grid: Path = None) -> bool:
    """The picture on disk is still the one Ally Hub made (the owner hasn't replaced it since)."""
    grid = grid or steam_grid_dir()
    want = ((art_made().get(str(appid)) or {}).get("hashes") or {}).get(kind)
    files = _grid_files(appid, kind, grid)
    if not want or len(files) != 1:
        return False
    try:
        return _sha(files[0].read_bytes()) == want
    except OSError:
        return False


def art_made() -> dict:
    return read_json(ART_MADE, {}) or {}


def is_self_shortcut(s: dict) -> bool:
    return s.get("name", "").strip().lower() == "ally hub" or "allyhub" in s.get("exe", "").lower()


# --- icons out of Windows programs (PE resources) ---

def _u16(b, o):
    return int.from_bytes(b[o:o + 2], "little")


def _u32(b, o):
    return int.from_bytes(b[o:o + 4], "little")


def pe_icon_entries(data: bytes) -> list:
    """The images of a Windows program's first icon group: [(size, bpp, image bytes)], biggest first."""
    try:
        if data[:2] != b"MZ":
            return []
        pe = _u32(data, 0x3C)
        if data[pe:pe + 4] != b"PE\0\0":
            return []
        coff = pe + 4
        nsec, optsz = _u16(data, coff + 2), _u16(data, coff + 16)
        opt = coff + 20
        magic = _u16(data, opt)
        dd = opt + (96 if magic == 0x10B else 112 if magic == 0x20B else 0)
        if dd == opt:
            return []
        res_rva = _u32(data, dd + 16)
        secs = []
        for i in range(nsec):
            s = opt + optsz + 40 * i
            secs.append((_u32(data, s + 12), max(_u32(data, s + 8), _u32(data, s + 16)), _u32(data, s + 20)))

        def off(rva):
            for va, size, raw in secs:
                if va <= rva < va + size:
                    return rva - va + raw
            return None

        base = off(res_rva)
        if base is None:
            return []

        def entries(d):
            n = _u16(data, d + 12) + _u16(data, d + 14)
            return [(_u32(data, d + 16 + 8 * k), _u32(data, d + 20 + 8 * k)) for k in range(min(n, 4096))]

        def leaf(o):                 # follow subdirectories down to the first data entry
            for _ in range(4):
                if not o & 0x80000000:
                    e = base + o
                    start = off(_u32(data, e))
                    return data[start:start + _u32(data, e + 4)] if start is not None else b""
                sub = entries(base + (o & 0x7FFFFFFF))
                if not sub:
                    return b""
                o = sub[0][1]
            return b""

        icons, groups = {}, []
        for tid, toff in entries(base):
            if tid in (3, 14) and toff & 0x80000000:
                for nid, noff in entries(base + (toff & 0x7FFFFFFF)):
                    blob = leaf(noff)
                    if tid == 3 and not nid & 0x80000000:
                        icons[nid] = blob
                    elif tid == 14:
                        groups.append(blob)
        for g in groups:
            out = []
            for k in range(_u16(g, 4)):
                e = 6 + 14 * k
                if e + 14 > len(g):
                    break
                size = g[e] or 256
                img = icons.get(_u16(g, e + 12))
                if img:
                    out.append((size, _u16(g, e + 6), img))
            if out:
                return sorted(out, key=lambda t: (t[0], t[1]), reverse=True)
    except (IndexError, ValueError):
        pass
    return []


def _png_encode(w: int, h: int, rgba: bytes) -> bytes:
    import struct
    import zlib
    raw = b"".join(b"\0" + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def _dib_to_png(dib: bytes) -> Optional[bytes]:
    """A classic icon bitmap (1/4/8/24/32-bit, bottom-up, AND mask for transparency) as a PNG."""
    try:
        hsize = _u32(dib, 0)
        w = int.from_bytes(dib[4:8], "little", signed=True)
        h = abs(int.from_bytes(dib[8:12], "little", signed=True)) // 2
        bpp = _u16(dib, 14)
        if not (0 < w <= 512 and 0 < h <= 512) or bpp not in (1, 4, 8, 24, 32):
            return None
        ncol = (_u32(dib, 32) or (1 << bpp)) if bpp <= 8 else 0
        pal = dib[hsize:hsize + 4 * ncol]
        px = hsize + 4 * ncol
        stride = ((w * bpp + 31) // 32) * 4
        mstride = ((w + 31) // 32) * 4
        mask = px + stride * h
        out = bytearray(w * h * 4)
        any_alpha = False
        for y in range(h):
            row = px + (h - 1 - y) * stride
            for x in range(w):
                if bpp == 32:
                    b, g, r, a = dib[row + 4 * x:row + 4 * x + 4]
                    any_alpha |= a > 0
                elif bpp == 24:
                    b, g, r = dib[row + 3 * x:row + 3 * x + 3]
                    a = 255
                else:
                    bit = x * bpp
                    idx = (dib[row + bit // 8] >> (8 - bpp - bit % 8)) & ((1 << bpp) - 1)
                    b, g, r = pal[4 * idx:4 * idx + 3] if 4 * idx + 3 <= len(pal) else (0, 0, 0)
                    a = 255
                o = (y * w + x) * 4
                out[o:o + 4] = bytes((r, g, b, a))
        if bpp != 32 or not any_alpha:          # transparency lives in the AND mask
            for y in range(h):
                row = mask + (h - 1 - y) * mstride
                for x in range(w):
                    if row + x // 8 < len(dib) and dib[row + x // 8] >> (7 - x % 8) & 1:
                        out[(y * w + x) * 4 + 3] = 0
                    elif bpp == 32:
                        out[(y * w + x) * 4 + 3] = 255
        return _png_encode(w, h, bytes(out))
    except (IndexError, ValueError):
        return None


def exe_icon_png(exe) -> Optional[bytes]:
    """The biggest icon inside a Windows .exe as PNG bytes, or None."""
    p = Path(str(exe).strip().strip('"'))
    try:
        if not p.is_file() or p.stat().st_size > 150 * 1024 * 1024:
            return None
        data = p.read_bytes()
    except OSError:
        return None
    for _size, _bpp, img in pe_icon_entries(data):
        if img.startswith(b"\x89PNG"):
            return img
        png = _dib_to_png(img)
        if png:
            return png
    return None


def _png_pixels(png: bytes):
    """(w, h, rgba) for plain 8-bit PNGs (what icons are), or None."""
    import struct
    import zlib
    try:
        if not png.startswith(b"\x89PNG"):
            return None
        pos, idat, pal, trns = 8, b"", b"", b""
        w = h = depth = ctype = interlace = 0
        while pos + 8 <= len(png):
            n, t = struct.unpack(">I4s", png[pos:pos + 8])
            d = png[pos + 8:pos + 8 + n]
            if t == b"IHDR":
                w, h, depth, ctype, _c, _f, interlace = struct.unpack(">IIBBBBB", d)
            elif t == b"PLTE":
                pal = d
            elif t == b"tRNS":
                trns = d
            elif t == b"IDAT":
                idat += d
            pos += 12 + n
        chans = {6: 4, 2: 3, 3: 1, 0: 1, 4: 2}.get(ctype)
        if depth != 8 or interlace or not chans or w * h > 1024 * 1024:
            return None
        raw = zlib.decompress(idat)
        stride = w * chans
        prev = bytearray(stride)
        out = bytearray()
        for y in range(h):
            f = raw[y * (stride + 1)]
            line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
            for i in range(stride):
                a = line[i - chans] if i >= chans else 0
                b = prev[i]
                c = prev[i - chans] if i >= chans else 0
                if f == 1:
                    line[i] = (line[i] + a) & 255
                elif f == 2:
                    line[i] = (line[i] + b) & 255
                elif f == 3:
                    line[i] = (line[i] + (a + b) // 2) & 255
                elif f == 4:
                    pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                    line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
            for x in range(w):
                px = line[x * chans:(x + 1) * chans]
                if ctype == 6:
                    out += px
                elif ctype == 2:
                    out += px + b"\xff"
                elif ctype == 4:
                    out += bytes((px[0], px[0], px[0], px[1]))
                elif ctype == 0:
                    out += bytes((px[0], px[0], px[0], 255))
                else:
                    i = px[0]
                    rgb = pal[3 * i:3 * i + 3] or b"\0\0\0"
                    out += rgb + bytes((trns[i] if i < len(trns) else 255,))
            prev = line
        return w, h, bytes(out)
    except Exception:
        return None


def icon_color(png: Optional[bytes]) -> str:
    """The icon's main color (saturated, opaque pixels count most), for the art's background."""
    px = _png_pixels(png) if png else None
    if not px:
        return ART_FALLBACK_COLOR
    w, h, rgba = px
    step = max(1, (w * h) // 4096)
    tot = r_s = g_s = b_s = 0.0
    for i in range(0, w * h, step):
        r, g, b, a = rgba[4 * i:4 * i + 4]
        if a < 160:
            continue
        _hh, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        wgt = (s * v) ** 2 + 0.002
        tot += wgt
        r_s, g_s, b_s = r_s + r * wgt, g_s + g * wgt, b_s + b * wgt
    if tot <= 0:
        return ART_FALLBACK_COLOR
    r, g, b = r_s / tot, g_s / tot, b_s / tot
    hh, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    if s < 0.15:                                      # grey or black icons: keep them on a calm slate
        return "#475569"
    r, g, b = colorsys.hsv_to_rgb(hh, max(s, 0.55), min(max(v, 0.75), 0.95))
    return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))


# --- the art itself, as SVG (only features Qt's SVG renderer supports: no filters, no nested <svg>) ---

def _mix(c1: str, c2: str, t: float) -> str:
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * t) for x, y in zip(a, b))


def _xml(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _wrap_title(name: str, width: float, size: int, lines: int = 2):
    """Pick a font size and line breaks so the name fits (rough width: 0.56 em per character)."""
    for sz in range(size, 22, -2):
        per = max(1, int(width / (sz * 0.56)))
        out, cur = [], ""
        for word in name.split():
            if cur and len(cur) + 1 + len(word) > per:
                out.append(cur)
                cur = word
            else:
                cur = (cur + " " + word).strip()
        out.append(cur)
        if len(out) <= lines and all(len(x) <= per for x in out):
            return sz, out
    return 22, [name[:40]]


def _icon_svg(x, y, size, icon_png: Optional[bytes], glyph: str, color: str) -> str:
    if icon_png:
        data = base64.b64encode(icon_png).decode()
        return (f'<image x="{x}" y="{y}" width="{size}" height="{size}" '
                f'xlink:href="data:image/png;base64,{data}"/>')
    s = size / 24
    return (f'<rect x="{x}" y="{y}" width="{size}" height="{size}" rx="{size * 0.22:.0f}" fill="{color}"/>'
            f'<g transform="translate({x + size * 0.2:.1f},{y + size * 0.2:.1f}) scale({s * 0.6:.3f})" fill="none" '
            f'stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{glyph}</g>')


def _title_svg(lines, x, y, size, anchor="middle", gap=1.15) -> str:
    out = ""
    for i, line in enumerate(lines):
        yy = y + i * size * gap
        out += (f'<text x="{x}" y="{yy + 3:.0f}" font-family="{ART_FONT}" font-size="{size}" font-weight="700" '
                f'text-anchor="{anchor}" fill="#000000" fill-opacity="0.35">{_xml(line)}</text>'
                f'<text x="{x}" y="{yy:.0f}" font-family="{ART_FONT}" font-size="{size}" font-weight="700" '
                f'text-anchor="{anchor}" fill="#ffffff">{_xml(line)}</text>')
    return out


def art_svgs(name: str, icon_png: Optional[bytes] = None, color: str = None, glyph: str = "") -> dict:
    """{kind: (svg, width, height)} for a tile: tall cover, wide banner, hero and logo, plus the icon tile
    when the program has no icon of its own."""
    c = color or icon_color(icon_png)
    deep, mid = _mix(c, "#05070d", 0.82), _mix(c, "#0b1020", 0.55)
    head = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '

    def defs(gx1, gy1, gx2, gy2, cx, cy, r):
        return (f'<defs><linearGradient id="bg" x1="{gx1}" y1="{gy1}" x2="{gx2}" y2="{gy2}">'
                f'<stop offset="0" stop-color="{mid}"/><stop offset="1" stop-color="{deep}"/></linearGradient>'
                f'<radialGradient id="glow" cx="{cx}" cy="{cy}" r="{r}">'
                f'<stop offset="0" stop-color="{c}" stop-opacity="0.55"/>'
                f'<stop offset="1" stop-color="{c}" stop-opacity="0"/></radialGradient></defs>')

    out = {}
    w, h = 600, 900
    sz, lines = _wrap_title(name, 520, 66)
    ty = 640 if len(lines) == 1 else 610
    out["portrait"] = (head + f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">' + defs(0, 0, 0.3, 1, 0.5, 0.36, 0.5) +
                       f'<rect width="{w}" height="{h}" fill="url(#bg)"/><rect width="{w}" height="{h}" fill="url(#glow)"/>'
                       + _icon_svg(170, 190, 260, icon_png, glyph, c) +
                       f'<rect x="250" y="{ty - sz - 34}" width="100" height="6" rx="3" fill="{c}"/>'
                       + _title_svg(lines, 300, ty, sz) + '</svg>', w, h)
    w, h = 920, 430
    sz, lines = _wrap_title(name, 500, 64)
    ty = 215 + sz * 0.35 - (len(lines) - 1) * sz * 0.57
    out["wide"] = (head + f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">' + defs(0, 0, 1, 1, 0.2, 0.5, 0.55) +
                   f'<rect width="{w}" height="{h}" fill="url(#bg)"/><rect width="{w}" height="{h}" fill="url(#glow)"/>'
                   + _icon_svg(80, 105, 220, icon_png, glyph, c) +
                   f'<rect x="360" y="{ty - sz - 26:.0f}" width="90" height="6" rx="3" fill="{c}"/>'
                   + _title_svg(lines, 360, ty, sz, "start") + '</svg>', w, h)
    w, h = 1920, 620
    out["hero"] = (head + f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">' + defs(0, 0, 1, 0.4, 0.74, 0.5, 0.42) +
                   f'<rect width="{w}" height="{h}" fill="url(#bg)"/><rect width="{w}" height="{h}" fill="url(#glow)"/>'
                   f'<g opacity="0.9">' + _icon_svg(1250, 110, 400, icon_png, glyph, c) + '</g></svg>', w, h)
    w, h = 1200, 300
    sz, lines = _wrap_title(name, 860, 110, lines=1)
    out["logo"] = (head + f'width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
                   + _icon_svg(20, 50, 200, icon_png, glyph, c)
                   + _title_svg(lines, 260, 150 + sz * 0.35, sz, "start") + '</svg>', w, h)
    if not icon_png:
        out["icon"] = (head + 'width="256" height="256" viewBox="0 0 256 256">'
                       + _icon_svg(0, 0, 256, None, glyph, c) + '</svg>', 256, 256)
    return out


def shortcut_icon_png(s: dict) -> Optional[bytes]:
    """The tile's own icon: from its .exe (NonSteamLaunchers stores run their Windows launcher), or an icon
    file Steam already points at."""
    for exe in (nsl_exe(s.get("name", "")), s.get("exe", "")):
        if exe and str(exe).strip().strip('"').lower().endswith(".exe"):
            png = exe_icon_png(exe)
            if png:
                return png
    icon = Path(str(s.get("icon", "")).strip('"'))
    if icon.suffix.lower() == ".png" and icon.is_file() and ART_DIR not in icon.parents:
        try:
            return icon.read_bytes()[:8 * 1024 * 1024]
        except OSError:
            return None
    if icon.suffix.lower() == ".exe":
        return exe_icon_png(icon)
    return None



def has_own_icon(s: dict) -> bool:
    """The tile already shows an icon someone chose (Steam can't draw .exe icons, and ours get replaced)."""
    icon = Path(str(s.get("icon", "")).strip().strip('"'))
    return (icon.suffix.lower() in (".png", ".ico", ".jpg", ".jpeg") and icon.is_file()
            and ART_DIR not in icon.parents)


def art_plan(only: list = None, redo: bool = False) -> dict:
    """What Fix artwork will do: {"tiles": n, "ours": n, "todo": [{appid, name, icon_png, color, self}]}.
    Never touches art the owner set himself: without redo only blank tiles; with redo only Ally Hub's own art."""
    tiles = steam_shortcuts()
    grid = steam_grid_dir()
    want = [n.lower() for n in only] if only else None
    todo, ours = [], 0
    for s in tiles:
        low = s["name"].lower()
        mine = art_is_ours(s["appid"], "portrait", grid)
        ours += mine
        if want is not None and not any(w == low or w in low for w in want):   # same matching as nsl_results
            continue
        if (redo and mine) or (not redo and not has_grid_art(s["appid"], grid)):
            png = None if is_self_shortcut(s) else shortcut_icon_png(s)
            todo.append({"appid": s["appid"], "name": s["name"], "icon_png": png, "self": is_self_shortcut(s),
                         "color": icon_color(png) if png else None, "has_icon": has_own_icon(s)})
    return {"tiles": len(tiles), "ours": ours, "todo": todo}

CEF_ART_JS = """(async () => {
  const id = %d, arts = %s, icon = %s, done = [];
  for (const [t, b64] of arts) {
    try { await SteamClient.Apps.ClearCustomArtworkForApp(id, t); } catch (e) {}
    try { await SteamClient.Apps.SetCustomArtworkForApp(id, b64, 'png', t); done.push(t); }
    catch (e) { console.error('Ally Hub art', id, t, e); }
  }
  if (icon) { try { await SteamClient.Apps.SetShortcutIcon(id, icon); done.push('icon'); } catch (e) {} }
  return JSON.stringify(done);
})()"""


def apply_art(appid: int, pngs: dict, icon_png: Optional[bytes] = None, name: str = "", mine: bool = False) -> dict:
    """Save the art to Steam's grid folder and hand it to Steam live. {"files": n, "live": bool}.
    Ally Hub's own art (mine=False) never replaces a picture the owner set himself, kind by kind;
    mine=True is the owner's own picture: it always goes in and isn't remembered as Ally Hub's."""
    grid = steam_grid_dir()
    pngs = {k: v for k, v in pngs.items() if k in ART_KINDS and v}
    if not mine and grid:
        pngs = {k: v for k, v in pngs.items() if not _grid_files(appid, k, grid) or art_is_ours(appid, k, grid)}
    files = 0
    if grid:
        try:
            grid.mkdir(parents=True, exist_ok=True)
        except OSError:
            grid = None
    for kind, png in pngs.items():
        if not grid:
            break
        try:
            for old in _grid_files(appid, kind, grid):      # Steam picks one: don't leave a .jpg next to ours
                old.unlink()
            (grid / ART_KINDS[kind][1].format(id=appid)).write_bytes(png)
            files += 1
        except OSError:
            pass
    icon_path = ""
    if icon_png:
        ART_DIR.mkdir(parents=True, exist_ok=True)
        p = ART_DIR / f"{appid}_icon.png"
        try:
            p.write_bytes(icon_png)
            icon_path = str(p)
        except OSError:
            pass
    arts = [[ART_KINDS[k][0], base64.b64encode(v).decode()] for k, v in pngs.items()]
    v = cef_eval(CEF_ART_JS % (int(appid), json.dumps(arts), json.dumps(icon_path)), timeout=60)
    try:
        live = json.loads(v) if v else None
    except ValueError:
        live = None
    with _ART_LOCK:
        made = art_made()
        if mine:
            made.pop(str(appid), None)
        else:
            rec = made.get(str(appid)) or {"hashes": {}}
            rec["name"], rec["t"] = name, int(time.time())
            rec.setdefault("hashes", {}).update({k: _sha(v) for k, v in pngs.items()})
            made[str(appid)] = rec
        write_json(ART_MADE, made)
    return {"files": files, "live": bool(live), "done": live or [], "kept": not pngs and not icon_path}


def nsl_results(names: list, shortcuts: set = None) -> dict:
    """After a run: {"missing": [not installed], "no_shortcut": [installed, but not in Steam]}."""
    shortcuts = {n.lower() for n in (shortcuts if shortcuts is not None else steam_shortcut_names())}
    missing = [n for n in names if n in NSL_STORES and not nsl_installed(n)]
    no_short = [n for n in names if n not in missing
                and not any(n.lower() == s or n.lower() in s for s in shortcuts)]
    return {"missing": missing, "no_shortcut": no_short}


def nsl_log_tail(lines: int = 120) -> str:
    text = read_text(NSL_LOG)
    out = "\n".join(text.splitlines()[-lines:])
    rc, journal = run_quiet(["journalctl", "--user", "-u", "nslgamescanner", "-n", "25", "--no-pager"], timeout=10)
    if journal:
        out += "\n\n--- scanner service ---\n" + journal
    out += f"\n\n--- account ---\nuserdata: {steam_user_id3() or 'not found'}; " \
           f"shortcuts.vdf: {'yes' if (shortcuts_vdf() and shortcuts_vdf().exists()) else 'no'}; " \
           f"steam debugger: {'on' if cef_eval('1+1', timeout=3) == 2 else 'off'}"
    return out


# ----- leftovers -----

def _du(path: Path) -> int:
    rc, out = run_quiet(["du", "-sb", str(path)], timeout=30)
    try:
        return int(out.split()[0]) if rc == 0 and out else 0
    except ValueError:
        return 0


def nsl_leftovers() -> list:
    """What uninstalled launchers left behind. Each: {label, path, size, warn}. Never anything a still
    installed launcher (or the games inside it) needs."""
    out = []
    installed = [n for n in NSL_STORES if nsl_installed(n)]
    # own prefixes ("separate" mode) whose launcher is gone
    for name, (rel, own, _a, _u) in NSL_STORES.items():
        d = COMPATDATA / own
        exe = nsl_exe(name)
        if d.exists() and not (exe and str(d) + "/" in str(exe)):
            out.append({"label": f"{name}'s old Proton prefix", "path": d, "size": _du(d), "warn": ""})
    shared = COMPATDATA / NSL_SHARED
    if shared.exists() and not any(nsl_exe(n) and NSL_SHARED in str(nsl_exe(n)) for n in NSL_STORES):
        out.append({"label": "Shared launcher prefix (no store left in it)", "path": shared, "size": _du(shared),
                    "warn": "Also removes any games you installed through those stores."})
    if NSL_DOWNLOADS.exists():
        out.append({"label": "Leftover installer downloads", "path": NSL_DOWNLOADS, "size": _du(NSL_DOWNLOADS),
                    "warn": ""})
    if not installed and NSL_SCANNER.exists():
        for p in (NSL_SCANNER, NSL_USER_DIR / "Modules", NSL_ENV, NSL_USER_DIR / "nslgamescanner.service"):
            if p.exists():
                out.append({"label": f"Game scanner files ({p.name})", "path": p, "size": _du(p), "warn": ""})
    for f in (HOME / ".steam/root/userdata").glob("*/config/shortcuts.vdf_backups"):
        old = sorted(f.glob("*"), key=lambda p: p.stat().st_mtime)[:-3]       # keep the newest 3
        for p in old:
            out.append({"label": "Old shortcut backup", "path": p, "size": _du(p), "warn": ""})
    return out


def nsl_clean_cmd(paths: list) -> Optional[str]:
    """Delete the chosen leftovers (all inside the home folder, no password)."""
    home = str(HOME) + "/"
    safe = [str(p) for p in paths if str(p).startswith(home) and str(p) != str(HOME)
            and (str(p).startswith(str(COMPATDATA) + "/") or str(p).startswith(str(NSL_USER_DIR) + "/")
                 or str(p).startswith(str(NSL_DOWNLOADS)) or "/shortcuts.vdf_backups/" in str(p))]
    if not safe:
        return None
    parts = []
    if any("nslgamescanner" in p or p == str(NSL_SCANNER) for p in safe):
        parts.append("systemctl --user disable --now nslgamescanner.service 2>/dev/null; true")
    parts.append("rm -rf -- " + " ".join(shlex.quote(p) for p in safe))
    parts.append("systemctl --user daemon-reload 2>/dev/null; echo 'Leftovers cleaned.'")
    return "; ".join(parts)


# ==========================================================================
# Storage saver: where the space went, and what can safely go
# Steam never cleans up after uninstalled games: their shader caches, Proton prefixes and half-finished
# downloads stay behind. Everything here is inside the home folder or a library on the SD card (both the
# user's own), so no password. Prefixes can hold save files, so they start unticked.
# ==========================================================================

TRASH_DIR = HOME / ".local/share/Trash"


def _acf_values(text: str) -> dict:
    return {k.lower(): v for k, v in re.findall(r'^\s*"(\w+)"\s+"([^"]*)"', text, re.M)}


def library_app_ids() -> set:
    """Every app Steam lists in its libraries, including ones on an SD card that isn't inserted right now."""
    text = read_text(STEAM_ROOT / "steamapps/libraryfolders.vdf")
    ids = set()
    for lib in (parse_vdf_text(text).get("libraryfolders", {}).values() if text else []):
        if isinstance(lib, dict):
            ids |= {k for k in (_ci(lib, "apps") or {}) if k.isdigit()}
    return ids


def steam_apps() -> list:
    """Installed Steam apps across every library: [{appid, name, lib, dir, size}] (size from Steam's manifest)."""
    out, seen = [], set()
    for lib in steam_library_dirs():
        for f in sorted(lib.glob("appmanifest_*.acf")):
            v = _acf_values(read_text(f))
            aid = v.get("appid") or f.stem.split("_", 1)[-1]
            if not aid.isdigit() or aid in seen:
                continue
            seen.add(aid)
            try:
                size = int(v.get("sizeondisk") or 0)
            except ValueError:
                size = 0
            out.append({"appid": aid, "name": v.get("name") or f"App {aid}", "lib": lib,
                        "dir": lib / "common" / v.get("installdir", ""), "size": size})
    return out


def shortcut_ids() -> set:
    """Ids of every non-Steam tile (their prefixes and shader caches are in use, not leftovers)."""
    ids = set()
    for f in (HOME / ".steam/root/userdata").glob("*/config/shortcuts.vdf"):
        try:
            ids.update(str(s["appid"]) for s in _vdf_shortcuts(f.read_bytes()))
        except OSError:
            pass
    return ids


def compat_tools_in_use() -> set:
    """Proton builds Steam is set to use (per game, or as the default "0" entry) in config.vdf."""
    text = read_text(STEAM_ROOT / "config/config.vdf") or read_text(HOME / ".steam/root/config/config.vdf")
    mapping = _ci(parse_vdf_text(text), "InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping")
    return {str(v.get("name") or v.get("Name") or "") for v in (mapping or {}).values()
            if isinstance(v, dict)} - {""}


def tool_names(folder: Path) -> set:
    """The names Steam knows a compatibility tool by: its folder and the ids in its compatibilitytool.vdf."""
    names = {folder.name}
    tools = _ci(parse_vdf_text(read_text(folder / "compatibilitytool.vdf")), "compatibilitytools", "compat_tools")
    if isinstance(tools, dict):
        names |= set(tools)
    return names


def tools_in_use_folders() -> set:
    """Resolved folders of every tool a game uses, plus anything a symlinked tool points at."""
    used = compat_tools_in_use()
    keep = set()
    for root in _tool_dirs():
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for p in entries:
            try:
                if p.is_symlink():
                    keep.add(p.resolve())
                elif p.is_dir() and tool_names(p) & used:
                    keep.add(p.resolve())
            except OSError:
                pass
    return keep


def _du_many(paths: list) -> dict:
    """Sizes of many folders with one du call: {path string: bytes}."""
    paths = [str(p) for p in paths if Path(p).exists()]
    out = {}
    for i in range(0, len(paths), 200):
        rc, text = run_quiet(["du", "-sb", "--", *paths[i:i + 200]], timeout=300)
        for line in (text or "").splitlines():
            size, _, path = line.partition("\t")
            if size.isdigit():
                out[path] = int(size)
    return out


def _proton_family(name: str) -> str:
    """"GE-Proton10-25" -> "ge-proton", "proton-cachyos-10.0-..." -> "proton-cachyos"."""
    return re.split(r"\d", name.lower(), maxsplit=1)[0].rstrip("-_. ") or name.lower()


def _tool_dirs() -> list:
    out = []
    for d in COMPAT_TOOL_DIRS:
        try:
            r = d.resolve()
        except OSError:
            continue
        if r not in out:
            out.append(r)
    return out


def app_names(ids: list) -> dict:
    """Names of games that are no longer installed, from Steam's own library (needs its debugger)."""
    if not ids:
        return {}
    v = cef_eval("JSON.stringify(%s.map(i=>[i,(window.appStore?.GetAppOverviewByAppID(+i)||{}).display_name||'']))"
                 % json.dumps([str(i) for i in ids]))
    try:
        return {str(k): n for k, n in json.loads(v) if n} if v else {}
    except (ValueError, TypeError):
        return {}


def storage_scan() -> dict:
    """{"games": [...biggest first], "items": [...cleanup candidates], "drives": [...]}."""
    libs = steam_library_dirs()
    apps = steam_apps()
    installed = {a["appid"] for a in apps} | library_app_ids()
    shorts = shortcut_ids()
    extra = {}                                   # appid -> {"shaders": [paths], "prefix": [paths]}
    leftovers = []                               # (kind, appid, path)
    for lib in libs:
        for kind in ("shadercache", "compatdata"):
            try:
                entries = [d for d in (lib / kind).iterdir() if d.is_dir()]
            except OSError:
                continue
            for d in entries:
                bk = PREFIX_BACKUP.match(d.name) if kind == "compatdata" else None
                if bk:
                    leftovers.append(("backup", bk.group(1), d))
                    continue
                if not d.name.isdigit() or d.name == "0":
                    continue
                if d.name in installed:
                    extra.setdefault(d.name, {"shaders": [], "prefix": []})[
                        "shaders" if kind == "shadercache" else "prefix"].append(d)
                elif d.name not in shorts:
                    leftovers.append((kind, d.name, d))
        try:
            for d in (lib / "downloading").iterdir():
                if d.is_dir() and d.name.isdigit():
                    leftovers.append(("downloading", d.name, d))
        except OSError:
            pass
    in_use = tools_in_use_folders()
    protons = []
    for root in _tool_dirs():
        try:
            protons += [p for p in root.iterdir() if p.is_dir() and not p.is_symlink()]
        except OSError:
            pass
    newest = {}
    for p in protons:
        fam = _proton_family(p.name)
        if fam not in newest or parse_version(p.name) > parse_version(newest[fam].name):
            newest[fam] = p
    sizes = _du_many([p for e in extra.values() for ps in e.values() for p in ps] +
                     [p for _k, _a, p in leftovers] + protons + [TRASH_DIR])
    games = []
    for a in apps:
        e = extra.get(a["appid"], {"shaders": [], "prefix": []})
        sh = sum(sizes.get(str(p), 0) for p in e["shaders"])
        pf = sum(sizes.get(str(p), 0) for p in e["prefix"])
        games.append(dict(a, shaders=sh, prefix=pf, total=a["size"] + sh + pf,
                          shader_paths=e["shaders"], lib=str(a["lib"]), dir=str(a["dir"])))
    games.sort(key=lambda g: g["total"], reverse=True)
    names = app_names(sorted({aid for _k, aid, _p in leftovers if aid not in installed}))
    items = []
    for kind, aid, p in leftovers:
        who = names.get(aid) or f"a removed game (app {aid})"
        size = sizes.get(str(p), 0)
        if kind == "shadercache":
            items.append({"label": f"Shader cache of {who}", "path": p, "size": size, "warn": "", "group": "safe"})
        elif kind == "backup":
            who = names.get(aid) or next((a["name"] for a in apps if a["appid"] == aid), f"app {aid}")
            items.append({"label": f"Old Windows files of {who} (set aside by a reset)", "path": p, "size": size,
                          "group": "check", "warn": "Holds that game's saves from before the reset, if it kept "
                                                    "them there."})
        elif kind == "compatdata":
            items.append({"label": f"Windows files of {who}", "path": p, "size": size, "group": "check",
                          "warn": "Can hold save files for games without Steam Cloud. Keep it if you might "
                                  "reinstall."})
        elif aid in installed:
            items.append({"label": f"Unfinished update for {names.get(aid) or next((a['name'] for a in apps if a['appid'] == aid), aid)}",
                          "path": p, "size": size, "group": "check",
                          "warn": "Steam downloads it again next time it updates the game."})
        else:
            items.append({"label": f"Unfinished download of {who}", "path": p, "size": size, "warn": "",
                          "group": "safe"})
    for p in protons:
        if p.resolve() not in in_use and newest.get(_proton_family(p.name)) is not p:
            items.append({"label": f"{p.name} (no game uses it, a newer one is installed)", "path": p,
                          "size": sizes.get(str(p), 0), "warn": "", "group": "safe"})
    trash = sizes.get(str(TRASH_DIR), 0)
    if trash > 1024 * 1024:
        items.append({"label": "Desktop Mode trash", "path": TRASH_DIR, "size": trash, "warn": "", "group": "safe"})
    items = [i for i in items if i["size"] > 0]
    items.sort(key=lambda i: (i["group"] != "safe", -i["size"]))
    drives, devs = [], set()
    for p in [HOME] + [lib for lib in libs if lib.exists()]:
        try:
            dev = os.stat(p).st_dev
            if dev in devs:
                continue
            devs.add(dev)
            u = shutil.disk_usage(p)
            sd = str(p).startswith("/run/media/")
            drives.append({"label": "SD card" if sd else "Internal storage", "path": str(p),
                           "free": u.free, "total": u.total})
        except OSError:
            pass
    return {"games": games, "items": items, "drives": drives}


def _storage_safe(p: str, ctx: dict) -> bool:
    """Only the kinds of folders storage_scan offers, checked again right before deleting (the library may
    have changed since the scan): never a game, a prefix in use, a Proton in use, a symlink, or anything else."""
    path = Path(p)
    if path == TRASH_DIR:
        return True
    if ".." in path.parts or path.is_symlink():
        return False
    if path.parent in _tool_dirs() or path.parent in COMPAT_TOOL_DIRS:
        return path.name not in ("", ".", "..") and path.resolve() not in ctx["tools"]
    if path.parent.parent not in ctx["libs"]:
        return False
    kind, name = path.parent.name, path.name
    if kind == "compatdata" and PREFIX_BACKUP.match(name):
        return True
    if not name.isdigit():
        return False
    if kind in ("shadercache", "downloading"):
        return True                          # rebuilt / re-downloaded by Steam: safe even for installed games
    return kind == "compatdata" and name not in ctx["installed"] and name not in ctx["shorts"]


def storage_clean_cmd(paths: list) -> Optional[str]:
    ctx = {"libs": steam_library_dirs(), "tools": tools_in_use_folders(), "shorts": shortcut_ids(),
           "installed": {a["appid"] for a in steam_apps()} | library_app_ids()}
    safe = [str(p) for p in paths if _storage_safe(str(p), ctx)]
    if not safe:
        return None
    parts = ["rc=0"]
    for p in safe:
        if Path(p) == TRASH_DIR:
            parts.append(f"rm -rf -- {shlex.quote(p + '/files')} {shlex.quote(p + '/info')} "
                         f"{shlex.quote(p + '/expunged')} || rc=1; mkdir -p {shlex.quote(p + '/files')} "
                         f"{shlex.quote(p + '/info')}")
        else:
            parts.append(f"rm -rf -- {shlex.quote(p)} || rc=1")
    parts.append('[ "$rc" = 0 ] && echo "Space freed."; exit $rc')
    return "; ".join(parts)



# ==========================================================================
# Game settings: per-game launch options as switches, the Proton picker, and "Game won't start?" help
# Everything is applied through Steam itself (SetAppLaunchOptions / SpecifyCompatTool over its local
# debugger), because Steam rewrites its own files and would undo direct edits.
# ==========================================================================

LSFG_WRAPPER = HOME / "lsfg"          # the launcher script decky-lsfg-vk puts in the home folder
# key -> (title, what it does, kind, token). "env" tokens go before %command%, "wrap" tokens right before it.
GAME_TOGGLES = {
    "fsr4": ("FSR 4 upgrade", "Games with FSR 3.1 use AMD's sharper FSR 4 instead. Looks much better, costs a "
             "few frames. Needs GE-Proton or Proton-CachyOS.", "env", "PROTON_FSR4_UPGRADE=1"),
    "lsfg": ("Frame generation", "Lossless Scaling frame generation for this game. Set the multiplier in its "
             "Decky plugin.", "wrap", "~/lsfg"),
    "deck": ("Steam Deck mode", "Tells the game it runs on a handheld, so many use their handheld presets and "
             "on-screen keyboard.", "env", "SteamDeck=1"),
    "wined3d": ("Older game fix", "Draws with WineD3D instead of DXVK. Try it if an old DirectX 9 or 10 game "
                "crashes or shows black screens.", "env", "PROTON_USE_WINED3D=1"),
    "log": ("Troubleshooting log", "Proton writes a log of the next launch, which Ally Hub can attach to a "
            "report.", "env", "PROTON_LOG=1"),
}
STEAM_TOOL_NAMES = re.compile(r"^(Proton|Steam Linux Runtime|Steamworks Common|SteamVR)", re.I)
PREFIX_BACKUP = re.compile(r"^(\d+)_allyhub_backup_(\d+)$")

_TOKEN = re.compile(r'''(?:[^\s"']+|"[^"]*"|'[^']*')+''')


def _env_key(tok: str) -> str:
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=", tok)
    return m.group(1) if m else ""


def split_launch(opts: str) -> tuple:
    """(tokens before %command%, text after it, had %command%). Without %command% Steam treats the whole
    string as arguments for the game."""
    opts = opts or ""
    if "%command%" in opts:
        pre, post = opts.split("%command%", 1)
        return _TOKEN.findall(pre), post, True
    return [], (" " + opts.strip()) if opts.strip() else "", False


def launch_parseable(opts: str) -> bool:
    """The switches can only edit launch options they can split cleanly (no stray quotes)."""
    pre, _post, had = split_launch(opts)
    if not had:
        return True
    head = (opts or "").split("%command%", 1)[0]
    return re.sub(r"\s+", "", "".join(pre)) == re.sub(r"\s+", "", head)


def steam_appid_of(game) -> Optional[int]:
    """The Steam app id for a running game id: non-Steam games carry their tile's id in the top 32 bits."""
    try:
        n = int(game)
    except (TypeError, ValueError):
        return None
    return n >> 32 if n > 0xFFFFFFFF else n


def launch_flags(opts: str) -> set:
    pre, _post, _had = split_launch(opts)
    on = set()
    for key, (_t, _d, kind, tok) in GAME_TOGGLES.items():
        if kind == "env" and tok in pre:
            on.add(key)
        elif kind == "wrap" and any(t in (tok, str(HOME / tok[2:])) for t in pre):
            on.add(key)
    return on


def set_launch_flags(opts: str, keys: set) -> str:
    """The same launch options with exactly these switches on. Everything else the owner typed is kept: only
    our exact tokens are removed (a turned-on switch also replaces other values of its own variable)."""
    pre, post, had = split_launch(opts)
    ours = {tok for _t, _d, _k, tok in GAME_TOGGLES.values()}
    ours |= {str(HOME / tok[2:]) for _t, _d, kind, tok in GAME_TOGGLES.values() if kind == "wrap"}
    turning_on = {_env_key(GAME_TOGGLES[k][3]) for k in keys if k in GAME_TOGGLES and GAME_TOGGLES[k][2] == "env"}
    keep = [t for t in pre if t not in ours and _env_key(t) not in turning_on]
    env = [GAME_TOGGLES[k][3] for k in GAME_TOGGLES if k in keys and GAME_TOGGLES[k][2] == "env"]
    wrap = [GAME_TOGGLES[k][3] for k in GAME_TOGGLES if k in keys and GAME_TOGGLES[k][2] == "wrap"]
    lead = env + [t for t in keep if _env_key(t)] + [t for t in keep if not _env_key(t)] + wrap
    if not lead:
        if not post.strip():
            return ""
        return ("%command%" + post).strip() if had else post.strip()
    return (" ".join(lead) + " %command%" + post).rstrip()


def parse_vdf_text(text: str) -> dict:
    """Steam's text VDF (localconfig.vdf, config.vdf) as nested dicts."""
    root, stack, key = {}, [], None
    cur = root
    for m in re.finditer(r'"((?:[^"\\]|\\.)*)"|([{}])', text):
        if m.group(2) == "{":
            new = {}
            cur[key if key is not None else ""] = new
            stack.append(cur)
            cur, key = new, None
        elif m.group(2) == "}":
            cur = stack.pop() if stack else root
            key = None
        else:
            s = m.group(1).replace('\\"', '"').replace("\\\\", "\\")
            if key is None:
                key = s
            else:
                cur[key] = s
                key = None
    return root


def _ci(d: dict, *path):
    for p in path:
        if not isinstance(d, dict):
            return {}
        d = next((v for k, v in d.items() if k.lower() == p.lower()), {})
    return d


def _local_apps() -> dict:
    id3 = steam_user_id3()
    if not id3:
        return {}
    text = read_text(HOME / ".steam/root/userdata" / id3 / "config/localconfig.vdf")
    return _ci(parse_vdf_text(text), "UserLocalConfigStore", "Software", "Valve", "Steam", "apps") if text else {}


def game_choices() -> list:
    """Games to pick from, most recently played first: installed Steam games and non-Steam tiles."""
    local = _local_apps()
    out = []
    for a in steam_apps():
        if STEAM_TOOL_NAMES.match(a["name"]):
            continue
        try:
            last = int((local.get(a["appid"]) or {}).get("LastPlayed") or 0)
        except (ValueError, AttributeError):
            last = 0
        out.append({"appid": int(a["appid"]), "name": a["name"], "kind": "steam", "last": last})
    f = shortcuts_vdf()
    try:
        tiles = _vdf_shortcuts(f.read_bytes()) if f and f.exists() else []
    except OSError:
        tiles = []
    for s in tiles:
        if not is_self_shortcut(s):
            out.append({"appid": s["appid"], "name": s["name"], "kind": "shortcut", "last": s.get("last", 0)})
    out.sort(key=lambda g: (-g["last"], g["name"].lower()))
    return out


CEF_GAME_JS = """(async () => {
  const id = %d;
  const details = await new Promise(res => {
    let done = false, h = null;
    const finish = d => { if (done) return; done = true; try { h && h.unregister(); } catch (e) {} res(d); };
    try { h = SteamClient.Apps.RegisterForAppDetails(id, d => finish(d)); } catch (e) { finish(null); }
    setTimeout(() => finish(null), 4000);
  });
  let tools = [];
  try { tools = (await SteamClient.Apps.GetAvailableCompatTools(id)) || []; } catch (e) {}
  return JSON.stringify({
    found: !!details,
    options: details ? (details.strLaunchOptions || "") : "",
    tool: details ? (details.strCompatToolName || "") : "",
    tools: tools.map(t => [t.strToolName, t.strDisplayName || t.strToolName])
  });
})()"""

CEF_SET_GAME_JS = """(async () => {
  const id = %d, opts = %s, tool = %s, done = [];
  try { await SteamClient.Apps.SetAppLaunchOptions(id, opts); done.push('options'); } catch (e) {}
  if (tool !== null) { try { await SteamClient.Apps.SpecifyCompatTool(id, tool); done.push('tool'); } catch (e) {} }
  return JSON.stringify(done);
})()"""


def game_settings(appid: int, kind: str = "steam") -> dict:
    """{"options", "tool", "tools": [(name, label)], "live"}. live False: Steam's debugger is off, so the
    values come from Steam's files and can't be saved."""
    v = cef_eval(CEF_GAME_JS % int(appid), timeout=15)
    try:
        d = json.loads(v) if v else None
    except ValueError:
        d = None
    if isinstance(d, dict) and d.get("found"):
        return {"options": d.get("options", ""), "tool": d.get("tool", ""),
                "tools": [tuple(t) for t in d.get("tools") or [] if isinstance(t, list) and len(t) == 2],
                "live": True}
    if kind == "shortcut":
        f = shortcuts_vdf()
        try:
            tiles = _vdf_shortcuts(f.read_bytes()) if f and f.exists() else []
        except OSError:
            tiles = []
        opts = next((s.get("options", "") for s in tiles if s["appid"] == int(appid)), "")
    else:
        opts = (_local_apps().get(str(appid)) or {}).get("LaunchOptions", "")
    cfg = parse_vdf_text(read_text(STEAM_ROOT / "config/config.vdf"))
    entry = _ci(cfg, "InstallConfigStore", "Software", "Valve", "Steam", "CompatToolMapping", str(appid))
    tool = entry.get("name", "") if isinstance(entry, dict) else ""
    return {"options": opts if isinstance(opts, str) else "", "tool": tool, "tools": [], "live": False}


def apply_game_settings(appid: int, options: str, tool: Optional[str] = None) -> list:
    """Hand the new launch options (and Proton choice, "" = Steam's default) to Steam. Returns what took."""
    v = cef_eval(CEF_SET_GAME_JS % (int(appid), json.dumps(options), json.dumps(tool)), timeout=20)
    try:
        return json.loads(v) if v else []
    except ValueError:
        return []


def game_prefixes(appid) -> list:
    return [lib / "compatdata" / str(appid) for lib in steam_library_dirs() if (lib / "compatdata" / str(appid)).is_dir()]


def reset_prefix_cmd(appid) -> Optional[str]:
    """Move the game's Windows files aside (never deleted): Steam builds fresh ones on the next launch, and
    the old folder stays as a backup Storage can clear later."""
    dirs = game_prefixes(appid)
    if not dirs:
        return None
    stamp = time.strftime("%Y%m%d%H%M%S")
    return " && ".join(f"mv -- {shlex.quote(str(d))} {shlex.quote(str(d.parent / f'{d.name}_allyhub_backup_{stamp}'))}"
                       for d in dirs) + " && echo 'Done. Steam makes fresh Windows files on the next launch.'"


def proton_log(appid) -> str:
    """The tail of Proton's log for this game (PROTON_LOG=1 writes ~/steam-<appid>.log)."""
    p = HOME / f"steam-{int(appid)}.log"
    try:
        data = p.read_bytes()
    except OSError:
        return ""
    return data[-200000:].decode("utf-8", "replace")



# ==========================================================================
# Quick Access panel: a small Decky plugin (Ally Hub in the ••• menu while you play)
# Its files live here, inside core.py, so every installed copy gets them with a normal update. The plugin
# only talks to the agent's local socket (CONTROL_SOCK, this user only). Bump QAM_VERSION when they change.
# ==========================================================================

QAM_VERSION = "1.0.3"
QAM_DIR = HOME / "homebrew/plugins/AllyHub"
QAM_STAGE = DATA_DIR / "qam-plugin"
QAM_PLUGIN_JSON = r'''{
  "name": "Ally Hub",
  "author": "Ravenor907",
  "flags": [],
  "api_version": 1,
  "publish": {
    "tags": ["ally", "utility"],
    "description": "Ally Hub in the Quick Access menu: status, per-game switches, Game Boost, lighting and save backups.",
    "image": ""
  }
}
'''
QAM_MAIN_PY = r'''# Ally Hub's Quick Access panel: a thin bridge to the Ally Hub agent running on this handheld.
# Talks only to the agent's local socket (owned by this user, mode 0600). No network.
import asyncio
import json
import os

try:
    import decky
    HOME = decky.DECKY_USER_HOME
    log = decky.logger
except Exception:                     # outside Decky (tests)
    import logging
    HOME = os.path.expanduser("~")
    log = logging.getLogger("allyhub")

SOCK = os.path.join(HOME, ".local/share/allyhub/agent.sock")


async def _ask(req: dict) -> dict:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(SOCK), timeout=3)
    except (OSError, asyncio.TimeoutError):
        return {"error": "agent"}
    try:
        writer.write(json.dumps(req).encode() + b"\n")
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), timeout=25)
        return json.loads(line or b"{}")
    except (OSError, ValueError, asyncio.TimeoutError) as e:
        log.warning(f"Ally Hub agent request failed: {e!r}")
        return {"error": "agent"}
    finally:
        writer.close()


class Plugin:
    async def status(self) -> dict:
        return await _ask({"op": "status"})

    async def action(self, name: str, data: dict = None) -> dict:
        return await _ask({"op": "action", "name": str(name), "data": data or {}})

    async def _main(self):
        log.info("Ally Hub panel loaded")

    async def _unload(self):
        pass
'''
QAM_INDEX_JS = r'''// Ally Hub's Quick Access panel. Plain JavaScript on Decky's own React and UI library (no build step).
// Lucide "gamepad-2" icon (ISC License, lucide.dev).
const React = window.SP_REACT;
const h = React.createElement;
const { useState, useEffect, useRef } = React;
const { PanelSection, PanelSectionRow, ToggleField, SliderField, DropdownItem, ButtonItem, Field, staticClasses } = window.DFL;
// The same hand-shake @decky/api does. API 2 adds useQuickAccessVisible; older Decky builds still answer.
const API = window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit.connect(2, "Ally Hub");
const useVisible = API.useQuickAccessVisible || (() => true);

const call = (method, ...args) => API.call(method, ...args).catch((e) => ({ error: String(e) }));
const toast = (body) => { try { API.toaster.toast({ title: "Ally Hub", body }); } catch (e) {} };

const GAME_SWITCHES = [
  ["fsr4", "FSR 4 upgrade", "Sharper upscaling. Needs GE-Proton or Proton-CachyOS."],
  ["lsfg", "Frame generation", "Lossless Scaling. Set the multiplier in its plugin."],
  ["deck", "Steam Deck mode", "Handheld presets and on-screen keyboard."],
];

function Icon() {
  return h("svg", { viewBox: "0 0 24 24", width: "1em", height: "1em", fill: "none", stroke: "currentColor",
                    strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" },
    h("line", { x1: 6, x2: 10, y1: 11, y2: 11 }), h("line", { x1: 8, x2: 8, y1: 9, y2: 13 }),
    h("line", { x1: 15, x2: 15.01, y1: 12, y2: 12 }), h("line", { x1: 18, x2: 18.01, y1: 10, y2: 10 }),
    h("path", { d: "M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4 4 0 0 0 17.32 5z" }));
}

function temp(v) { return v === null || v === undefined ? "–" : `${Math.round(v)}°`; }

// ---- look (1.3.7.2): a hero card for battery and temps, pills, colored game header ----
const ACCENT = "linear-gradient(135deg, #e11d48 0%, #8b5cf6 100%)";
const card = { borderRadius: "12px", padding: "12px 14px", margin: "4px 0 6px",
               background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.08)" };
function pct(text) { const m = /(\d+)/.exec(text || ""); return m ? Math.min(100, +m[1]) : null; }
function Pill(label, value, key) {
  return h("div", { key, style: { flex: 1, textAlign: "center", padding: "6px 4px", borderRadius: "10px",
                                   background: "rgba(0,0,0,0.25)" } },
    h("div", { style: { fontSize: "11px", opacity: 0.7, textTransform: "uppercase", letterSpacing: "0.04em" } }, label),
    h("div", { style: { fontSize: "16px", fontWeight: 700, marginTop: "2px" } }, value));
}
function Hero(s) {
  const p = pct(s.battery);
  const color = p === null ? "#8b5cf6" : p <= 15 ? "#ef4444" : p <= 35 ? "#f59e0b" : "#22c55e";
  const charging = /charg/i.test(s.battery || "") && !/dis/i.test(s.battery || "");
  return h("div", { style: { ...card, background: "rgba(255,255,255,0.05)" } },
    h("div", { style: { display: "flex", alignItems: "baseline", justifyContent: "space-between" } },
      h("div", { style: { fontSize: "30px", fontWeight: 800, lineHeight: 1 } }, p === null ? "–" : `${p}%`,
        charging ? h("span", { style: { fontSize: "14px", marginLeft: "6px", opacity: 0.8 } }, "⚡") : null),
      h("div", { style: { fontSize: "13px", opacity: 0.8, textAlign: "right" } },
        s.time_left && s.time_left !== "n/a" ? `${s.time_left} left` : (charging ? "Charging" : ""))),
    h("div", { style: { height: "6px", borderRadius: "3px", background: "rgba(255,255,255,0.12)", margin: "10px 0" } },
      h("div", { style: { width: `${p || 0}%`, height: "100%", borderRadius: "3px", background: color,
                          transition: "width 0.4s" } })),
    h("div", { style: { display: "flex", gap: "6px" } },
      Pill("CPU", temp(s.cpu), "c"), Pill("GPU", temp(s.gpu), "g"),
      Pill(s.watts ? "Power" : "Fan", s.watts ? `${s.watts} W` : (s.fan ? `${s.fan}` : "–"), "w")));
}
function GameHeader(name, live) {
  return h("div", { style: { ...card, background: ACCENT, border: "none", color: "#fff" } },
    h("div", { style: { fontSize: "11px", opacity: 0.85, textTransform: "uppercase", letterSpacing: "0.06em" } }, "Now playing"),
    h("div", { style: { fontSize: "17px", fontWeight: 800, marginTop: "2px", overflow: "hidden",
                        textOverflow: "ellipsis", whiteSpace: "nowrap" } }, name),
    h("div", { style: { fontSize: "11px", opacity: 0.85, marginTop: "4px" } },
      live ? "Switches apply the next time you start it." : "Reading this game's settings…"));
}

function Content() {
  const [s, setS] = useState(null);
  const [level, setLevel] = useState(null);       // brightness while the slider moves
  const [speed, setSpeed] = useState(null);       // effect speed while the slider moves
  const spd = useRef(null);
  const busy = useRef(false);
  const bright = useRef(null);
  const seq = useRef(0);
  const visible = useVisible();
  const load = async () => {
    const mine = ++seq.current;                   // an older, slower answer never overwrites a newer one
    const r = await call("status");
    if (mine === seq.current) setS(r);
  };
  useEffect(() => {
    if (!visible) return undefined;               // no polling while the menu is closed
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [visible]);
  useEffect(() => () => { clearTimeout(bright.current); clearTimeout(spd.current); }, []);
  const act = async (name, data = {}, quiet = false) => {
    if (busy.current) return;                     // one change at a time; controls stay enabled for focus
    busy.current = true;
    const r = await call("action", name, data);
    busy.current = false;
    if (r && r.message && !quiet) toast(r.message);
    else if (r && r.error) toast("Ally Hub's background helper didn't answer.");
    load();
  };

  if (!s) return h(PanelSection, null, h(PanelSectionRow, null, h(Field, { label: "Loading…", focusable: true })));
  if (s.error) {
    return h(PanelSection, { title: "Ally Hub" },
      h(PanelSectionRow, null, h(Field, { focusable: true, label: "Ally Hub's background helper isn't running",
        description: "Open Ally Hub and turn it on under Settings → General." })));
  }

  const sections = [];
  sections.push(h(PanelSection, { key: "status" }, h(PanelSectionRow, null, Hero(s))));

  if (s.game) {
    const flags = s.game_flags;
    const rows = [h(PanelSectionRow, { key: "name" }, GameHeader(s.game_name || "This game", !!flags))];
    if (flags) {
      for (const [key, title, desc] of GAME_SWITCHES) {
        if (key === "lsfg" && !s.lsfg && !flags.includes(key)) continue;
        rows.push(h(PanelSectionRow, { key }, h(ToggleField, { label: title, description: desc,
          checked: flags.includes(key), disabled: !s.game_live,
          onChange: (on) => act("game_flag", { key, on }) })));
      }
    }
    sections.push(h(PanelSection, { title: "This game", key: "game" }, ...rows));
  }

  sections.push(h(PanelSection, { title: "Performance", key: "perf" },
    h(PanelSectionRow, null, h(ToggleField, { label: "Game Boost", checked: !!s.boost,
      description: s.boost && s.boost_note ? `CPU: ${s.boost_note}` : "Performance CPU setting while you play.",
      onChange: (on) => act("boost", { on }) }))));

  if (s.lighting === "allyhub") {
    const opts = (s.effects || []).map((n) => ({ data: n, label: n }));
    sections.push(h(PanelSection, { title: "Lighting", key: "light" },
      h(PanelSectionRow, null, h(DropdownItem, { label: "Effect", rgOptions: opts,
        selectedOption: s.effect, strDefaultLabel: s.effect || "Pick one",
        onChange: (o) => act("preset", { name: o.data }) })),
      h(PanelSectionRow, null, h(SliderField, { label: "Brightness",
        value: level !== null ? level : Math.round((s.brightness || 0) / 2.55),
        min: 0, max: 100, step: 5, showValue: true, valueSuffix: "%",
        onChange: (v) => { setLevel(v); clearTimeout(bright.current);
          bright.current = setTimeout(async () => { await act("brightness", { value: Math.round(v * 2.55) }, true);
            setLevel(null); }, 400); } })),
      s.animated ? h(PanelSectionRow, null, h(SliderField, { label: "Speed",
        value: speed !== null ? speed : Math.round((s.speed || 1) * 100),
        min: 10, max: 300, step: 10, showValue: true, valueSuffix: "%",
        onChange: (v) => { setSpeed(v); clearTimeout(spd.current);
          spd.current = setTimeout(async () => { await act("speed", { value: v / 100 }, true);
            setSpeed(null); }, 400); } })) : null,
      h(PanelSectionRow, null, h(ToggleField, { label: "Battery rings", checked: !!(s.toggles || {}).battery_rings,
        description: "Rings show your battery level.",
        onChange: (on) => act("toggle", { key: "battery_rings", on }) })),
      h(PanelSectionRow, null, h(ToggleField, { label: "Low battery flash", checked: !!(s.toggles || {}).low_battery_flash,
        description: "Rings flash red at 15% or lower.",
        onChange: (on) => act("toggle", { key: "low_battery_flash", on }) })),
      h(PanelSectionRow, null, h(ButtonItem, { layout: "below", onClick: () => act("lights") }, "Lights off"))));
  }

  if (s.backup) {
    sections.push(h(PanelSection, { title: "Saves", key: "saves" },
      h(PanelSectionRow, null, h(ToggleField, { label: "Save time machine", checked: !!s.time_machine,
        description: "Snapshot a game's saves every time it starts.",
        onChange: (on) => act("toggle", { key: "time_machine", on }) })),
      h(PanelSectionRow, null, h(ButtonItem, { layout: "below", disabled: s.backup_running,
        onClick: () => act("backup") }, s.backup_running ? "Backing up…" : "Back up saves now"))));
  }
  return h("div", null, ...sections);
}

export default function () {
  return {
    name: "Ally Hub",
    titleView: h("div", { className: staticClasses.Title }, "Ally Hub"),
    content: h(Content),
    icon: h(Icon),
    onDismount() {},
  };
}
'''


def qam_files() -> dict:
    return {"plugin.json": QAM_PLUGIN_JSON, "main.py": QAM_MAIN_PY, "dist/index.js": QAM_INDEX_JS,
            "package.json": json.dumps({"name": "allyhub-panel", "version": QAM_VERSION, "type": "module",
                                        "license": "GPL-3.0"}, indent=2) + "\n"}


def qam_installed() -> Optional[str]:
    """The installed panel's version, or None."""
    try:
        return json.loads((QAM_DIR / "package.json").read_text()).get("version") or "0"
    except (OSError, ValueError):
        return "0" if (QAM_DIR / "plugin.json").exists() else None


def qam_stage() -> Path:
    shutil.rmtree(QAM_STAGE, ignore_errors=True)
    for name, text in qam_files().items():
        p = QAM_STAGE / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return QAM_STAGE


def qam_install_cmd() -> str:
    """Copy the panel into Decky's plugin folder (root's) and restart Decky so it shows up."""
    stage, dest = shlex.quote(str(qam_stage())), shlex.quote(str(QAM_DIR))
    return (f'sudo mkdir -p {shlex.quote(str(QAM_DIR.parent))} && sudo rm -rf {dest} && '
            f'sudo cp -r {stage} {dest} && '
            'sudo systemctl restart plugin_loader && echo "Quick Access panel ready."')


def qam_uninstall_cmd() -> str:
    return (f"sudo rm -rf {shlex.quote(str(QAM_DIR))} && sudo systemctl restart plugin_loader && "
            "echo 'Quick Access panel removed.'")


def emudeck_uninstall_cmd() -> str:
    """EmuDeck's own guided uninstaller exists only after its first-run setup. Before that, all there is to
    remove is the app file the installer downloaded (and its shortcuts)."""
    u = shlex.quote(str(HOME / ".config/EmuDeck/backend/uninstall.sh"))
    files = " ".join(shlex.quote(str(p)) for p in (EMUDECK_PATH, HOME / "Desktop/EmuDeck.desktop",
                                                     HOME / ".local/share/applications/EmuDeck.desktop"))
    return (f'if [ -f {u} ]; then bash {u}; '
            f'else rm -f -- {files} && echo "EmuDeck was never set up, so only its app was removed."; fi')



# ==========================================================================
# Save time machine: a snapshot of a game's saves every time it starts, restorable from Game Mode
# Ludusavi does the work (it knows where thousands of games keep their saves, Proton prefixes included).
# Snapshots live in their own folder with Ludusavi's per-game retention (--full-limit), so they never mix with
# the scheduled full backups.
# ==========================================================================

TM_DIR = BACKUP_DIR / "time-machine"
TM_BEFORE_RESTORE = BACKUP_DIR / "before-restore"     # what was there right before a restore
TM_STATE = DATA_DIR / "time_machine.json"             # {title: {"t", "rc", "game"}}
TM_TITLES = DATA_DIR / "ludusavi_titles.json"         # game id / name -> Ludusavi title (or "" = not known)
TM_MIN_GAP_S = 600                                    # one snapshot per game per 10 minutes (relaunch loops)


def ludusavi_cmd(*args) -> list:
    return ["flatpak", "run", LUDUSAVI_ID, *args]


def ludusavi_ready() -> bool:
    return run_quiet(["flatpak", "info", LUDUSAVI_ID])[0] == 0


def ludusavi_title(appid: Optional[int] = None, name: str = "") -> str:
    """Ludusavi's title for a game ("" when Ludusavi doesn't know it). Steam games by id, others by name."""
    key = f"steam:{appid}" if appid and appid < 0x80000000 else f"name:{name.strip().lower()}"
    cache = read_json(TM_TITLES, {}) or {}
    if key in cache:
        return cache[key]
    if key == "name:":
        return ""

    def ask(args):
        """(title, definitely-unknown). Only a clear "unknown game" answer is remembered as unknown, so a
        timeout or an offline first run is simply tried again next time."""
        rc, out = run_quiet(["nice", "-n", "19"] + ludusavi_cmd("find", "--api", *args), timeout=90)
        try:
            data = json.loads(out) if out else {}
        except ValueError:
            return "", False
        title = next(iter(data.get("games") or {}), "") if isinstance(data, dict) else ""
        unknown = bool(((data.get("errors") or {}) if isinstance(data, dict) else {}).get("unknownGames"))
        return title, unknown and not title

    title, unknown = ask(["--steam-id", str(appid)]) if key.startswith("steam:") else ("", True)
    if not title and name.strip():
        title, unknown2 = ask(["--normalized", name.strip()])   # exact name first, then normalized (never fuzzy)
        unknown = unknown and unknown2
    if title or unknown:
        cache[key] = title
        write_json(TM_TITLES, cache)
    return title


def ludusavi_title_cached(appid: Optional[int] = None, name: str = "") -> str:
    """The title from earlier lookups only (never runs Ludusavi), for quick checks in the window."""
    cache = read_json(TM_TITLES, {}) or {}
    key = f"steam:{appid}" if appid and appid < 0x80000000 else f"name:{name.strip().lower()}"
    return cache.get(key, "")


def tm_backup_args(title: str, keep: int, path: Path = None) -> list:
    return ludusavi_cmd("backup", "--force", "--no-cloud-sync", "--path", str(path or TM_DIR),
                        "--full-limit", str(max(1, min(50, int(keep)))), "--differential-limit", "0", "--api", title)


def tm_due(title: str) -> bool:
    last = ((read_json(TM_STATE, {}) or {}).get(title) or {}).get("t", 0)
    return time.time() - last > TM_MIN_GAP_S


def tm_record(title: str, rc: int, game: str = "") -> None:
    st = read_json(TM_STATE, {}) or {}
    st[title] = {"t": time.time(), "rc": rc, "game": game}
    write_json(TM_STATE, st)


def tm_snapshots(path: Path = None) -> dict:
    """{title: [{"name", "when", "locked"}...] newest first} from Ludusavi's own listing of a snapshot folder."""
    path = path or TM_DIR
    if not path.exists():
        return {}
    rc, out = run_quiet(ludusavi_cmd("backups", "--api", "--path", str(path)), timeout=120)
    try:
        games = json.loads(out).get("games") or {} if rc == 0 and out else {}
    except ValueError:
        return {}
    res = {}
    for title, info in games.items():
        backs = [b for b in (info or {}).get("backups") or [] if isinstance(b, dict) and b.get("name")]
        if backs:
            res[title] = sorted(backs, key=lambda b: b.get("when", ""), reverse=True)
    return res


def tm_restore_cmd(title: str, backup: str, undo: bool = False) -> str:
    """Restore one snapshot. What's there now is saved first (in its own folder) and the restore only runs if
    that worked, so every restore can be undone. undo=True restores that safety copy instead."""
    src = TM_BEFORE_RESTORE if undo else TM_DIR
    restore = " ".join(shlex.quote(a) for a in ludusavi_cmd("restore", "--force", "--no-cloud-sync", "--path",
                                                            str(src), "--backup", backup, title))
    done = f"echo {shlex.quote(('Undid the last restore of ' if undo else 'Restored ') + title + '.')}"
    if undo:
        return f"{restore} && {done}"
    before = " ".join(shlex.quote(a) for a in tm_backup_args(title, 3, TM_BEFORE_RESTORE)[:-2] + [title])
    return (f"mkdir -p {shlex.quote(str(TM_BEFORE_RESTORE))} && echo 'Saving your current saves first…' && "
            f"{before} && {restore} && {done}")


def when_text(iso: str) -> str:
    """'Today 14:32', 'Yesterday 21:05', 'Mar 3, 09:10' for a snapshot time."""
    import datetime
    try:
        t = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return iso or "?"
    now = datetime.datetime.now().astimezone()
    days = (now.date() - t.date()).days
    hm = t.strftime("%H:%M")
    return f"Today {hm}" if days == 0 else f"Yesterday {hm}" if days == 1 else t.strftime("%b %-d, ") + hm



# ==========================================================================
# Sleep guardian: how much battery each sleep costs, what woke the handheld, and sleeps that failed
# The agent notices a sleep from the gap between CLOCK_BOOTTIME (keeps counting while suspended) and
# CLOCK_MONOTONIC (doesn't), then compares the kernel's wakeup counters and suspend statistics from just before
# and just after. Everything read here is world-readable sysfs; the only fix (stop a USB device waking the
# handheld) is a udev rule in /etc, undone from the same page and by the uninstaller.
# ==========================================================================

POWER_ROOT = Path("/sys/power")
WAKEUP_ROOT = Path("/sys/class/wakeup")
SLEEP_LOG = DATA_DIR / "sleep_log.json"
SLEEP_KEEP = 60
NOWAKE_RULE = "/etc/udev/rules.d/71-allyhub-nowake.rules"
SLEEP_DRAIN_HIGH = 3.0          # % per hour while asleep that counts as a problem
SLEEP_STATS = ("success", "fail", "last_failed_dev", "last_failed_errno", "last_failed_step", "last_hw_sleep",
               "total_hw_sleep")


def suspend_stats() -> dict:
    out = {}
    for name in SLEEP_STATS:
        v = read_text(POWER_ROOT / "suspend_stats" / name).strip()
        out[name] = int(v) if v.lstrip("-").isdigit() else v
    return out


def wakeup_sources() -> dict:
    """{source dir name: {"name", "count", "devpath", "wake_file"}} for every wakeup source the kernel lists."""
    out = {}
    try:
        entries = list(WAKEUP_ROOT.iterdir())
    except OSError:
        return out
    for d in entries:
        count = read_text(d / "wakeup_count").strip()      # times it woke the system or stopped a sleep
        dev = ""
        try:
            if (d / "device").exists():
                dev = str((d / "device").resolve())
        except OSError:
            dev = ""
        wake = Path(dev) / "power/wakeup" if dev else None
        out[d.name] = {"name": read_text(d / "name").strip() or d.name, "count": int(count) if count.isdigit() else 0,
                       "devpath": dev[4:] if dev.startswith("/sys/") else dev,
                       "wake_file": str(wake) if wake and wake.exists() else ""}
    return out


def battery_level() -> Optional[float]:
    now, full = battery_energy_wh()
    if now and full:
        return round(100 * now / full, 2)
    b = battery_info()
    try:
        return float(b.get("capacity"))
    except (TypeError, ValueError):
        return None


def wake_counts() -> dict:
    """Just the wakeup counters, cheap enough to read every second: {source dir: count}."""
    out = {}
    try:
        entries = list(WAKEUP_ROOT.iterdir())
    except OSError:
        return out
    for d in entries:
        c = read_text(d / "wakeup_count").strip()
        out[d.name] = int(c) if c.isdigit() else 0
    return out


def wake_irq_name() -> str:
    """What the kernel says woke it last: /sys/power/pm_wakeup_irq, named through /proc/interrupts."""
    irq = read_text(POWER_ROOT / "pm_wakeup_irq").strip()
    if not irq.isdigit():
        return ""
    for line in read_text(Path("/proc/interrupts")).splitlines():
        parts = line.split()
        if parts and parts[0].rstrip(":") == irq:
            return " ".join(p for p in parts[1:] if not p.isdigit())[-60:] or f"IRQ {irq}"
    return f"IRQ {irq}"


def sleep_snapshot(full: bool = True) -> dict:
    """Suspend stats and wakeup counters. The agent takes a light one every second (so the "before" side is
    never stale, and the button press that started the sleep isn't blamed for waking it)."""
    snap = {"t": time.time(), "stats": suspend_stats(), "wc": wake_counts()}
    if full:
        snap["wake"] = wakeup_sources()
    return snap


def sleep_entry(pre: dict, post: dict, slept_s: float, pct_before, pct_after, charging: bool) -> dict:
    hours = slept_s / 3600
    drop = round(pct_before - pct_after, 2) if pct_before is not None and pct_after is not None else None
    names = {k: v["name"] for k, v in (post.get("wake") or {}).items()}
    c0, c1 = pre.get("wc") or {}, post.get("wc") or {}
    woke = [names.get(k, k) for k in c1 if k in c0 and c1[k] > c0[k]]
    if not woke and post.get("irq"):
        woke = [post["irq"]]
    s0, s1 = pre.get("stats", {}), post.get("stats", {})
    failed = isinstance(s1.get("fail"), int) and isinstance(s0.get("fail"), int) and s1["fail"] > s0["fail"]
    t0, t1 = s0.get("total_hw_sleep"), s1.get("total_hw_sleep")         # microseconds in hardware sleep
    hw = t1 - t0 if isinstance(t0, int) and isinstance(t1, int) and t1 >= t0 else None
    hw_pct = round(min(100.0, hw / 1e6 / slept_s * 100), 1) if hw and slept_s > 0 else None
    return {"end": round(post.get("t", time.time())), "slept": round(slept_s), "pct_before": pct_before,
            "pct_after": pct_after, "drop": drop, "charging": bool(charging),
            "per_hour": round(drop / hours, 2) if drop is not None and not charging and hours >= 0.25 else None,
            "woke_by": woke[:6], "failed": failed,
            "failed_dev": s1.get("last_failed_dev") if failed else "",
            "failed_step": s1.get("last_failed_step") if failed else "", "hw_sleep_pct": hw_pct}


def sleep_failure_entry(stats: dict) -> dict:
    """A sleep that never happened (the kernel gave up): no clock gap, so the agent records it from the stats."""
    return {"end": round(time.time()), "slept": 0, "pct_before": None, "pct_after": None, "drop": None,
            "charging": False, "per_hour": None, "woke_by": [], "failed": True,
            "failed_dev": stats.get("last_failed_dev") or "", "failed_step": stats.get("last_failed_step") or "",
            "hw_sleep_pct": None}


def record_sleep(entry: dict) -> None:
    log = read_json(SLEEP_LOG, []) or []
    log.append(entry)
    write_json(SLEEP_LOG, log[-SLEEP_KEEP:])


def sleep_log() -> list:
    log = read_json(SLEEP_LOG, []) or []
    return [e for e in log if isinstance(e, dict)]


def duration_text(seconds: float) -> str:
    m = int(seconds // 60)
    return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min" if m else f"{int(seconds)} s"


def _never_offer(source: dict) -> bool:
    """Devices Ally Hub never offers to stop: anything that isn't a USB device (power button, lid, the
    chipset), and USB root hubs (blocking one would stop every device on it, the built-in controller too)."""
    dev = source.get("devpath", "")
    return "/usb" not in dev or bool(re.search(r"/usb\d+$", dev)) or not source.get("wake_file")


def sleep_findings(log: list = None, sources: dict = None) -> list:
    """Plain-language problems with recent sleeps: [{"id", "title", "detail", "fix": {...} or None}]."""
    log = sleep_log() if log is None else log
    sources = wakeup_sources() if sources is None else sources
    recent = log[-12:]
    out = []
    long_ = [e for e in recent if e.get("per_hour") is not None and e.get("slept", 0) >= 3600]
    if long_:
        rates = sorted(e["per_hour"] for e in long_)
        med = rates[len(rates) // 2]
        if med > SLEEP_DRAIN_HIGH:
            last = long_[-1]
            detail = (f"About {med:.1f}% per hour while asleep. Last time it lost {last['drop']:.0f}% over "
                      f"{duration_text(last['slept'])}.")
            hw = [e["hw_sleep_pct"] for e in long_ if e.get("hw_sleep_pct") is not None]
            if hw and min(hw) < 80:
                detail += f" It only spent {min(hw):.0f}% of that time in its deepest sleep, so something keeps it busy."
            out.append({"id": "drain", "title": "Sleep uses a lot of battery", "detail": detail, "fix": None})
    shorts = [e for e in recent if 0 < e.get("slept", 0) < 180 and e.get("woke_by")]
    if len(shorts) >= 3:
        names = {}
        for e in shorts:
            for n in e["woke_by"]:
                names[n] = names.get(n, 0) + 1
        culprit = max(names, key=names.get)
        src = next((s for s in sources.values() if s["name"] == culprit), None)
        fix = None if not src or _never_offer(src) else {"kind": "nowake", "devpath": src["devpath"], "name": culprit}
        out.append({"id": "wakes", "title": f"{culprit} keeps waking the handheld",
                    "detail": f"{len(shorts)} recent sleeps ended within 3 minutes, woken by {culprit}."
                              + ("" if fix else " It's a system device, so it's best left alone; this was noted in "
                                                "the sleep details."), "fix": fix})
    fails = [e for e in recent if e.get("failed")]
    if fails:
        e = fails[-1]
        dev, step = e.get("failed_dev") or "", e.get("failed_step") or ""
        detail = "The handheld couldn't go to sleep" + (f" because of {dev}" if dev else "") + \
                 (f" (step: {step})" if step else "") + ". Send the sleep details so it can be looked at."
        out.append({"id": "failed", "title": "A sleep attempt failed", "detail": detail, "fix": None})
    return out


def _nowake_ok(d: str) -> bool:
    return d.startswith("/devices/") and "/usb" in d and not re.search(r"/usb\d+$", d) and \
        not any(c in d for c in '"\n\\')


def nowake_cmd(devpaths: list, allow: list = ()) -> Optional[str]:
    """Rewrite the rule file for exactly these USB devices (an empty list removes it) and apply it right away:
    blocked devices get wakeup disabled, devices taken off the list (`allow`) get it enabled again."""
    devpaths = sorted({d for d in devpaths if _nowake_ok(d)})
    allow = sorted({d for d in allow if _nowake_ok(d)} - set(devpaths))
    rule = shlex.quote(NOWAKE_RULE)
    sets = [f"echo disabled | sudo tee {shlex.quote('/sys' + d + '/power/wakeup')} >/dev/null" for d in devpaths] + \
           [f"echo enabled | sudo tee {shlex.quote('/sys' + d + '/power/wakeup')} >/dev/null" for d in allow]
    apply = f"{{ {' ; '.join(sets)} ; true; }} && " if sets else ""
    if not devpaths:
        return (f"sudo rm -f {rule} && sudo udevadm control --reload && {apply}"
                "echo 'Every device can wake the handheld again.'")
    lines = "".join(f'ACTION=="add|bind|change", SUBSYSTEM=="usb", DEVPATH=="{d}", ATTR{{power/wakeup}}="disabled"\n'
                    for d in devpaths)
    return (f"printf %s {shlex.quote(lines)} | sudo tee {rule} >/dev/null && sudo udevadm control --reload && "
            f"{apply}echo 'Saved.'")



# ==========================================================================
# First run: what a fresh install does on its own, and what's left for the user
# ==========================================================================

GAMEMODE_DESKTOP = HOME / ".local/share/applications/allyhub-gamemode.desktop"
LAUNCHER = HOME / ".local/bin/allyhub"


def gamemode_desktop_text() -> str:
    return ("[Desktop Entry]\nType=Application\nName=Ally Hub\n"
            f"Exec={LAUNCHER} --gamemode\nIcon={APP_DIR / 'allyhub.svg'}\nNoDisplay=true\nTerminal=false\n")


MENU_ENTRIES = (HOME / ".local/share/applications/allyhub.desktop", HOME / "Desktop/allyhub.desktop")


def tidy_menu_entry() -> bool:
    """Ally Hub shows once in the app menu, under Utilities. Installers before 1.4.3 listed three categories, so KDE
    showed it under Games, Utilities and System (the owner noticed). Fixes existing entries in place."""
    changed = False
    for p in MENU_ENTRIES:
        try:
            text = p.read_text()               # not read_text(): that strips, and the file keeps its layout
        except OSError:
            continue
        if text and re.search(r"^Categories=(?!Utility;$).*$", text, re.M):
            try:
                p.write_text(re.sub(r"^Categories=.*$", "Categories=Utility;", text, flags=re.M))
                changed = True
            except OSError:
                pass
    return changed


def in_steam_library() -> bool:
    return any(n.strip().lower() == "ally hub" for n in steam_shortcut_names())


def add_to_steam() -> str:
    """Put Ally Hub in the Game Mode library through SteamOS's own helper. Returns what happened."""
    if in_steam_library():
        return "already"
    tool = shutil.which("steamos-add-to-steam")
    if not tool or not LAUNCHER.exists():
        return "unavailable"
    GAMEMODE_DESKTOP.parent.mkdir(parents=True, exist_ok=True)
    GAMEMODE_DESKTOP.write_text(gamemode_desktop_text())
    try:
        subprocess.Popen([tool, str(GAMEMODE_DESKTOP)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        return "unavailable"
    return "added"


def start_agent(python: str) -> bool:
    AGENT_UNIT.parent.mkdir(parents=True, exist_ok=True)
    AGENT_UNIT.write_text(agent_unit_text(python))
    ok = run_quiet(["systemctl", "--user", "daemon-reload"], timeout=20)[0] == 0
    return ok and run_quiet(["systemctl", "--user", "enable", "--now", "allyhub-agent.service"], timeout=30)[0] == 0


def first_install(python: str) -> list:
    """Run by install.sh. Only on a brand new install (no settings yet): turn the agent on, put Ally Hub in the
    Game Mode library, and have the app open its setup on first launch. Updates and reinstalls change nothing."""
    if CONFIG_FILE.exists():
        return []
    update_config(lambda c: (c["agent"].__setitem__("enabled", True),
                             c.setdefault("setup", {}).__setitem__("done", False)))
    out = ["Background helper " + ("started" if start_agent(python) else "will start from the app")]
    res = add_to_steam()
    out.append({"added": "Added to your Game Mode library (Steam may take a moment to show it)",
                "already": "Already in your Game Mode library",
                "unavailable": "Add it to Game Mode later from the app's setup"}[res])
    return out


def setup_checklist(state: dict) -> list:
    """[(key, title, done)] for the Home 'Finish setting up' card and the setup page."""
    cfg = load_config()
    decky = CATALOG_BY_ID["decky"].check(state) if "decky" in CATALOG_BY_ID else False
    return [("password", "Set a sudo password", state.get("password") is not False),
            ("decky", "Install Decky Loader", bool(decky)),
            ("steam", "Put Ally Hub in your Game Mode library", in_steam_library()),
            ("agent", "Turn on the background helper", bool(cfg["agent"].get("enabled")) and agent_running())]


def decky_version(item, state: dict) -> str:
    """Installed version of a catalog Decky plugin, shown on its card ("" when unknown)."""
    if not getattr(item, "decky_names", None):
        return ""
    for key, info in state.get("decky", {}).items():
        if any(n in key or n in Path(info["dir"]).name.lower() for n in item.decky_names):
            return info.get("version", "")
    return ""


def decky_plugin_item(id, name, desc, monogram, color, install, names, warn="",
                      recommended=False) -> Item:
    return Item(
        id=id, name=name, category="Game Mode plugins", desc=desc, monogram=monogram,
        color=color, install=install, check=lambda s, n=names: bool(decky_match(n, s)),
        uninstall="decky", warn=warn, requires=("decky",), recommended=recommended,
        decky_names=names,
    )


TAILSCALE_INSTALL = (
    'tmp=$(mktemp -d) && git clone --depth 1 https://github.com/tailscale-dev/deck-tailscale '
    '"$tmp/dt" && cd "$tmp/dt" && sudo bash tailscale.sh; rc=$?; rm -rf "$tmp"; exit $rc'
)

CATALOG = [
    # ================= MODS =================
    Item(
        id="decky", name="Decky Loader", category="Essentials",
        desc="The plugin loader for Game Mode. Unlocks the Plugin Store page in Ally Hub "
             "and the plug icon in your Quick Access menu.",
        monogram="D", color="#8b5cf6",
        install=fetch_run("https://github.com/SteamDeckHomebrew/decky-installer/releases/latest/download/install_release.sh"),
        uninstall=fetch_run("https://github.com/SteamDeckHomebrew/decky-installer/releases/latest/download/uninstall.sh"),
        check=lambda s: DECKY_PATH.exists(),
        warn="SteamOS updates can remove Decky. Ally Hub's Update Guardian will spot it.",
        recommended=True,
    ),
    decky_plugin_item(
        "allycenter", "Ally Center",
        "Built for the ROG Ally: TDP presets, RGB effects, charge limit, battery health, "
        "temps and a screen-off download mode, all from the Quick Access menu.",
        "AC", "#e11d48",
        fetch_run("https://github.com/PixelAddictUnlocked/allycenter/raw/main/install.sh"),
        ("ally center", "allycenter"), recommended=True,
        warn="Use one TDP tool at a time: Ally Center, SimpleDeckyTDP or the SteamOS slider.",
    ),
    # Frame generation: the same builds Bazzite installs (ujust get-decky-lossless-scaling / get-framegen),
    # i.e. the latest stable GitHub release, not the Decky store's older copy or a pre-release.
    decky_plugin_item(
        "lsfg", "Lossless Scaling Frame Gen",
        "Doubles, triples or quadruples your frame rate in almost any game. The same build Bazzite "
        "installs: per-game profiles, a simple multiplier slider and launch options set for you.",
        "LS", "#8b5cf6",
        github_decky_install_cmd("xXJSONDeruloXx/decky-lsfg-vk", "Decky.LSFG-VK.zip", ("Decky LSFG-VK",)),
        ("lsfg",),
        warn="Needs Lossless Scaling from Steam (paid), switched to its lsfg-vk beta branch. "
             "After installing, open the plugin once and tap Install lsfg-vk.",
    ),
    decky_plugin_item(
        "framegen", "OptiScaler Frame Gen",
        "FSR 4, XeSS and frame generation for games that support DLSS, FSR or XeSS. Pick a game in "
        "the plugin and it sets the launch options for you. The same build Bazzite installs.",
        "OS", "#0ea5e9",
        github_decky_install_cmd("xXJSONDeruloXx/Decky-Framegen", "Decky-Framegen.zip",
                                 ("Decky-Framegen", "Decky Framegen")),
        ("framegen",),
        warn="Large download (about 190 MB). Works only in games with DLSS, FSR or XeSS.",
    ),
    decky_plugin_item(
        "simpledeckytdp", "SimpleDeckyTDP",
        "Per-game TDP profiles, GPU clock control and CPU boost/SMT toggles. "
        "Supports the Ally X through ASUS WMI.",
        "TDP", "#f97316",
        fetch_run("https://github.com/aarron-lee/SimpleDeckyTDP/raw/main/install.sh"),
        ("simpledeckytdp",),
        warn="Overlaps with Ally Center and SteamOS's own TDP slider. Pick one.",
    ),
    Item(
        id="nonsteamlaunchers", name="NonSteamLaunchers", category="Launchers & stores",
        desc="Adds Epic, GOG, EA App, Ubisoft Connect, Battle.net, Xbox Game Pass (cloud), Netflix, "
             "YouTube and more straight into your Steam library with artwork. Pick them on the Launchers page.",
        monogram="NS", color="#10b981", kind="run",
        install=fetch_run("https://raw.githubusercontent.com/moraroy/NonSteamLaunchers-On-Steam-Deck/main/NonSteamLaunchers.sh", "bash"),
        check=lambda s: False,
        warn="Restart Steam afterwards to see the new shortcuts.",
    ),
    Item(
        id="tailscale", name="Tailscale", category="Launchers & stores",
        desc="Private network between your devices. Stream your home PC with Moonlight from "
             "anywhere, or reach your Ally from your phone. Set it up on the Connect page.",
        monogram="Ts", color="#64748b",
        install=TAILSCALE_INSTALL,
        uninstall=('tmp=$(mktemp -d) && git clone --depth 1 https://github.com/tailscale-dev/deck-tailscale '
                   '"$tmp/dt" && cd "$tmp/dt" && sudo bash uninstall.sh; rc=$?; rm -rf "$tmp"; exit $rc'),
        check=lambda s: Path(TAILSCALE_BIN).exists(),
        requires=(),
    ),
    Item(
        id="emudeck", name="EmuDeck", category="Emulation",
        desc="Installs and configures dozens of emulators, builds ROM folders and adds "
             "games to Steam with artwork and controller profiles.",
        monogram="E", color="#f59e0b",
        install=fetch_run("https://raw.githubusercontent.com/dragoonDorise/EmuDeck/main/install.sh", "bash"),
        open_cmd=shlex.quote(str(EMUDECK_PATH)),
        check=lambda s: EMUDECK_PATH.exists(),
        uninstall=emudeck_uninstall_cmd(),
        warn="Pick EmuDeck or RetroDECK, not both. Remove runs EmuDeck's own uninstaller, which asks about "
             "backing up your saves and BIOS (best done in Desktop Mode).",
    ),
    flatpak_item("net.retrodeck.retrodeck", "RetroDECK", "Emulation",
                 "All-in-one retro platform in a single Flatpak. Cleaner and more "
                 "self-contained than EmuDeck.", "RD", "#ef4444"),
    flatpak_item("com.steamgriddb.SteamROMManager", "Steam ROM Manager", "Emulation",
                 "Add ROMs and non-Steam games to Steam with proper artwork.", "SR", "#eab308"),

    # ================= APPS =================
    flatpak_item("com.heroicgameslauncher.hgl", "Heroic Games Launcher", "Game launchers",
                 "Play your Epic, GOG and Amazon Prime Gaming libraries.",
                 "He", "#06b6d4", recommended=True),
    flatpak_item("net.lutris.Lutris", "Lutris", "Game launchers",
                 "One launcher for Battle.net, EA, Ubisoft, emulators and install scripts.",
                 "Lu", "#f59e0b"),
    flatpak_item("com.usebottles.bottles", "Bottles", "Game launchers",
                 "Run Windows apps and launchers in isolated Wine prefixes.", "B", "#ef4444"),
    flatpak_item("io.itch.itch", "itch.io", "Game launchers",
                 "The indie game store and its huge free library.", "it", "#fa5c5c"),
    flatpak_item("page.kramo.Cartridges", "Cartridges", "Game launchers",
                 "A clean library that pulls games from Steam, Heroic, Lutris and more.",
                 "Ca", "#a3e635"),
    flatpak_item("com.vysp3r.ProtonPlus", "ProtonPlus", "Compatibility",
                 "Install Proton-GE, Proton-CachyOS and other compatibility tools.",
                 "P+", "#a855f7", recommended=True),
    flatpak_item("net.davidotek.pupgui2", "ProtonUp-Qt", "Compatibility",
                 "The classic Proton-GE / Wine-GE manager for Steam, Heroic and Lutris.",
                 "PU", "#7c3aed"),
    flatpak_item("com.github.Matoking.protontricks", "Protontricks", "Compatibility",
                 "Install Windows runtimes and fixes into individual Proton games.", "Pt", "#6d28d9"),
    flatpak_item("io.github.unknownskl.greenlight", "Greenlight", "Cloud & streaming",
                 "Native Xbox Cloud Gaming and Xbox home streaming client. Perfect fit "
                 "for an Xbox Ally.", "XC", "#107c10", recommended=True),
    flatpak_item("com.google.Chrome", "Google Chrome", "Cloud & streaming",
                 "Best browser for GeForce NOW, Amazon Luna and web cloud gaming.", "C", "#22c55e"),
    flatpak_item("com.moonlight_stream.Moonlight", "Moonlight", "Cloud & streaming",
                 "Stream games from your gaming PC (Sunshine or Apollo host).", "M", "#0ea5e9"),
    flatpak_item("io.github.streetpea.chiaki-ng", "chiaki-ng", "Cloud & streaming",
                 "PlayStation Remote Play for PS4 and PS5.", "PS", "#2563eb"),
    flatpak_item("org.vinegarhq.Sober", "Sober", "More games",
                 "Run Roblox on Linux, with ads and telemetry off by default.", "Ro", "#e2e8f0"),
    flatpak_item("org.prismlauncher.PrismLauncher", "Prism Launcher", "More games",
                 "Minecraft Java with easy modpacks and multiple instances.", "Mc", "#16a34a"),
    flatpak_item("io.mrarm.mcpelauncher", "Minecraft Bedrock Launcher", "More games",
                 "Play Minecraft Bedrock Edition (needs a Google Play copy).", "MB", "#65a30d"),
    flatpak_item("com.discordapp.Discord", "Discord", "Social & media",
                 "Voice and chat with your friends.", "Di", "#6366f1"),
    flatpak_item("dev.vencord.Vesktop", "Vesktop", "Social & media",
                 "Discord with working screen share audio on Linux and better performance.",
                 "Ve", "#818cf8"),
    flatpak_item("com.spotify.Client", "Spotify", "Social & media",
                 "Music and podcasts.", "Sp", "#1db954"),
    flatpak_item("tv.kodi.Kodi", "Kodi", "Social & media",
                 "Full media center with a controller-friendly interface.", "K", "#17b2e7"),
    flatpak_item("tv.plex.PlexHTPC", "Plex HTPC", "Social & media",
                 "Plex's big-screen app, works great with a controller.", "Px", "#e5a00d"),
    flatpak_item("com.stremio.Stremio", "Stremio", "Social & media",
                 "Streaming hub for movies and shows.", "St", "#7b5bf5"),
    flatpak_item("io.github.radiolamp.mangojuice", "MangoJuice", "Utilities",
                 "Customize the MangoHud performance overlay without editing config files.",
                 "MJ", "#f472b6"),
    flatpak_item("com.github.mtkennerly.ludusavi", "Ludusavi", "Utilities",
                 "Back up your game saves. Powers Ally Hub's save snapshots and backups.",
                 "Ls", "#0891b2", recommended=True),
    flatpak_item("org.localsend.localsend_app", "LocalSend", "Utilities",
                 "AirDrop-style file transfer to your phone or PC over Wi-Fi.", "LS", "#14b8a6"),
    flatpak_item("com.obsproject.Studio", "OBS Studio", "Utilities",
                 "Record or stream your gameplay.", "OB", "#475569"),
    flatpak_item("com.github.tchx84.Flatseal", "Flatseal", "Utilities",
                 "Fine-tune Flatpak permissions.", "F", "#3b82f6"),
    flatpak_item("io.github.flattool.Warehouse", "Warehouse", "Utilities",
                 "Manage, downgrade and clean up Flatpak apps and leftover data.", "W", "#0d9488"),
]
CATALOG_BY_ID = {i.id: i for i in CATALOG}
LUDUSAVI_ID = "com.github.mtkennerly.ludusavi"

MOD_CATEGORIES = ["Essentials", "Game Mode plugins", "Launchers & stores", "Emulation"]
APP_CATEGORIES = ["Game launchers", "Compatibility", "Cloud & streaming", "More games",
                  "Social & media", "Utilities"]

FEATURED_PLUGINS = [
    "css loader", "steamgriddb", "protondb", "hltb", "storage cleaner",
    "tabmaster", "audio loader", "animation changer", "junk", "ludusavi", "sunshine",
    "decky recorder", "bluetooth", "free loader", "magicpods", "localsend",
]


def gather_state() -> dict:
    return {"flatpaks": installed_flatpaks(), "decky": installed_decky_plugins(), "decky_off": sorted(decky_disabled())}


# ---------- Turning Decky plugins off and on (without uninstalling) ----------
# Decky keeps the list in its own settings ("disabled_plugins" in ~/homebrew/settings/loader.json, plugin.json
# names) and only reads it at start, so the job stops Decky, edits the list as root, and starts it again.
DECKY_SETTINGS = HOME / "homebrew/settings/loader.json"
DECKY_SAFE_MODE = DATA_DIR / "decky_safe_mode.json"     # which plugins "Turn all off" turned off
_DECKY_TOGGLE_PY = (
    "import json,os,sys\n"
    "p,mode,names=sys.argv[1],sys.argv[2],json.loads(sys.argv[3])\n"
    "try:\n s=json.load(open(p))\nexcept Exception:\n s={}\n"
    "d=[n for n in s.get('disabled_plugins',[]) if n not in names]\n"
    "s['disabled_plugins']=d+(names if mode=='off' else [])\n"
    "os.makedirs(os.path.dirname(p),exist_ok=True)\n"
    "t=p+'.allyhub';json.dump(s,open(t,'w'),indent=4);os.replace(t,p)\n"
)


def decky_disabled() -> set:
    return set((read_json(DECKY_SETTINGS, {}) or {}).get("disabled_plugins") or [])


def decky_toggle_cmd(names: list, off: bool) -> Optional[str]:
    names = sorted({str(n) for n in names if n})
    if not names:
        return None
    return ("sudo systemctl stop plugin_loader; "
            f"sudo python3 -c {shlex.quote(_DECKY_TOGGLE_PY)} {shlex.quote(str(DECKY_SETTINGS))} "
            f"{'off' if off else 'on'} {shlex.quote(json.dumps(names))}; rc=$?; "
            "sudo systemctl start plugin_loader; "
            f"[ $rc = 0 ] && echo {shlex.quote(('Turned off: ' if off else 'Turned on: ') + ', '.join(names))}; exit $rc")


def decky_item_names(item, state: dict) -> list:
    """The plugin.json names behind a catalog item (what Decky's off list uses)."""
    dirs = set(decky_match(getattr(item, "decky_names", ()) or (), state))
    return [i["name"] for i in state.get("decky", {}).values() if i["dir"] in dirs]


def decky_remove_cmd(dirs: list) -> str:
    quoted = " ".join(shlex.quote(d) for d in dirs)
    return f"sudo rm -rf {quoted} && sudo systemctl restart plugin_loader"


def decky_store_install_cmd(url: str, sha256: str = "") -> str:
    """Install a Decky store plugin. With the store's sha256 the download is checked first, like Decky does."""
    q = shlex.quote(url)
    check = (f'echo {shlex.quote(sha256.lower() + "  ")}"$tmp/p.zip" | sha256sum -c --quiet - && '
             if re.fullmatch(r"[0-9a-fA-F]{64}", sha256 or "") else "")
    return (
        'tmp=$(mktemp -d) && '
        f'curl -fL -o "$tmp/p.zip" {q} && '
        + check +
        'python3 -m zipfile -e "$tmp/p.zip" "$tmp/out" && '
        'sudo mkdir -p "$HOME/homebrew/plugins" && '
        'for d in "$tmp/out"/*/; do n=$(basename "$d"); '
        'sudo rm -rf "$HOME/homebrew/plugins/$n"; '
        'sudo cp -r "$d" "$HOME/homebrew/plugins/$n"; '
        'sudo chown -R "$USER:$USER" "$HOME/homebrew/plugins/$n"; done && '
        'sudo systemctl restart plugin_loader; rc=$?; rm -rf "$tmp"; exit $rc'
    )


def store_latest_version(plugin: dict) -> Optional[dict]:
    vers = plugin.get("versions") or []
    if not vers:
        return None
    if all(x.get("created") for x in vers):
        return max(vers, key=lambda x: x["created"])
    return vers[0]


def store_artifact_hash(plugin: dict) -> str:
    """The store's sha256 for the latest version ("" when it has none)."""
    v = store_latest_version(plugin) or {}
    h = str(v.get("hash") or "")
    return h if re.fullmatch(r"[0-9a-fA-F]{64}", h) else ""


def store_artifact_url(plugin: dict) -> Optional[str]:
    v = store_latest_version(plugin)
    if not v:
        return None
    return v.get("artifact") or (DECKY_CDN.format(v["hash"]) if v.get("hash") else None)


# ==========================================================================
# Profiles (export / import your whole setup)
# ==========================================================================

SETTINGS_SNAP_DIR = BACKUP_DIR / "auto"


def snapshot_settings() -> Path:
    """Tar up settings we can read without root (no password). Keeps the 5 newest. Update Guardian runs this
    daily; Backups > Back up now runs it on demand."""
    SETTINGS_SNAP_DIR.mkdir(parents=True, exist_ok=True)
    out = SETTINGS_SNAP_DIR / f"settings-{time.strftime('%Y-%m-%d_%H%M%S')}.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for rel in ("homebrew/settings", ".config/allyhub", ".config/MangoHud"):
            base = HOME / rel
            if not base.exists():
                continue
            for root, _dirs, files in os.walk(base):
                for f in files:
                    p = Path(root) / f
                    try:
                        tar.add(p, arcname=str(p.relative_to(HOME)))
                    except (OSError, tarfile.TarError):
                        pass
    snaps = sorted(SETTINGS_SNAP_DIR.glob("settings-*.tar.gz"))
    for old in snaps[:-5]:
        old.unlink(missing_ok=True)
    return out


PROFILE_KEYS = ("theme", "rgb", "agent", "game_colors", "dock", "wol", "performance")
# Never shared in a profile and never taken from one: a profile can't switch on someone's remote with a PIN the
# sender knows, and doesn't hand out the PIN or the PC's network address.
PROFILE_PRIVATE = {"agent": ("remote", "remote_pin", "remote_port"), "wol": ("mac", "broadcast")}
FLATPAK_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+){2,}$")


def charge_limit_ok(value) -> Optional[str]:
    """A charge limit as a plain number 50-100, or None. Profiles are files from anywhere, so this is checked
    before it gets near a command."""
    v = str(value or "").strip()
    return v if re.fullmatch(r"\d{2,3}", v) and 50 <= int(v) <= 100 else None


def _profile_config(cfg: dict) -> dict:
    out = {}
    for k in PROFILE_KEYS:
        v = cfg.get(k)
        if isinstance(v, dict) and k in PROFILE_PRIVATE:
            v = {kk: vv for kk, vv in v.items() if kk not in PROFILE_PRIVATE[k]}
        out[k] = v
    return out


def build_profile(state: dict) -> dict:
    cfg = load_config()
    b = battery_info()
    return {
        "allyhub_profile": 1,
        "created": time.strftime("%Y-%m-%d %H:%M"),
        "device": device_name(),
        "flatpaks": sorted(state.get("flatpaks", [])),
        "catalog": sorted(i.id for i in CATALOG
                          if not i.id.count(".") and i.kind == "install" and i.check(state)),
        "decky_plugins": sorted(v["name"] for v in state.get("decky", {}).values()),
        "config": _profile_config(cfg),
        "system": {"charge_limit": b.get("limit") or "", "ssh": sshd_active()},
    }


def export_profile(state: dict) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKUP_DIR / f"profile-{time.strftime('%Y-%m-%d_%H%M')}.allyhub.json"
    path.write_text(json.dumps(build_profile(state), indent=2))
    return path


def profile_plan(profile: dict, state: dict) -> dict:
    """What importing this profile would add on this device."""
    def strings(key):
        v = profile.get(key)
        return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []
    system = profile.get("system") if isinstance(profile.get("system"), dict) else {}
    return {
        "catalog": [i for i in strings("catalog") if i in CATALOG_BY_ID and not CATALOG_BY_ID[i].check(state)],
        "flatpaks": [f for f in strings("flatpaks") if FLATPAK_ID_RE.match(f) and f not in state.get("flatpaks", set())],
        "decky_plugins": [p for p in strings("decky_plugins") if p.lower() not in state.get("decky", {})],
        "config": profile.get("config") if isinstance(profile.get("config"), dict) else {},
        "system": {"charge_limit": charge_limit_ok(system.get("charge_limit")) or "", "ssh": system.get("ssh") is True},
    }


def apply_profile_config(conf: dict) -> None:
    def fn(cfg):
        for k in PROFILE_KEYS:
            v = conf.get(k)
            if v is None or not isinstance(v, type(DEFAULT_CONFIG[k])):
                continue
            if isinstance(v, dict) and k in PROFILE_PRIVATE:
                v = {kk: vv for kk, vv in v.items() if kk not in PROFILE_PRIVATE[k]}
                v.update({kk: cfg[k][kk] for kk in PROFILE_PRIVATE[k] if kk in cfg.get(k, {})})
            cfg[k] = v
    update_config(fn)


# ==========================================================================
# Agent service
# ==========================================================================

def agent_unit_text(python: str) -> str:
    return (
        "[Unit]\nDescription=Ally Hub agent (lighting, automation, remote)\n"
        "After=graphical-session.target\n\n"
        "[Service]\nType=simple\n"
        f"ExecStart={python} {APP_DIR / 'allyhub.py'} --agent\n"
        "Restart=on-failure\nRestartSec=5\nNice=10\n\n"
        "[Install]\nWantedBy=default.target\n"
    )


def agent_running() -> bool:
    return service_active("allyhub-agent", user=True)


def pause_agent() -> bool:
    """Stop the background agent (a user service, no password) so it can't touch the lights during
    the light test. Returns True if it was running and should be started again."""
    if not agent_running():
        return False
    try:
        subprocess.run(["systemctl", "--user", "stop", "allyhub-agent.service"], capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return False
    return True


def resume_agent():
    try:
        subprocess.run(["systemctl", "--user", "start", "allyhub-agent.service"], capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        pass


def agent_state() -> dict:
    return read_json(AGENT_STATE, {}) or {}


# ==========================================================================
# Performance: Game Boost and Tune-up
# Ideas from CachyOS (game-performance, sysctl defaults) and Bazzite/CryoUtilities (zram, huge pages).
# SteamOS's root is read-only, so everything lives in /etc and /sys, goes through one password prompt,
# and has an undo. Values are written only when the kernel has the setting.
# ==========================================================================

CPUFREQ_ROOT = Path("/sys/devices/system/cpu/cpufreq")
SYSCTL_ROOT = Path("/proc/sys")
THP_ROOT = Path("/sys/kernel/mm/transparent_hugepage")
MODULES_ROOT = Path("/lib/modules")
PROC_SWAPS = Path("/proc/swaps")
MEMINFO = Path("/proc/meminfo")
NTSYNC_DEV = Path("/dev/ntsync")
BOOST_STATE = DATA_DIR / "boost_state.json"
TUNEUP_BEFORE = DATA_DIR / "tuneup_before.json"
BOOST_TMPFILES = "/etc/tmpfiles.d/allyhub-boost.conf"
TUNEUP_SYSCTL = "/etc/sysctl.d/99-zz-allyhub.conf"      # sorts after SteamOS's own 99-* files, so ours win
TUNEUP_SWAP_SYSCTL = "/etc/sysctl.d/99-zz-allyhub-zram.conf"   # only written once zram really is the swap
TUNEUP_TMPFILES = "/etc/tmpfiles.d/allyhub-tuneup.conf"
TUNEUP_ZRAM_SCRIPT = "/etc/allyhub/zram.sh"
TUNEUP_ZRAM_UNIT = "/etc/systemd/system/allyhub-zram.service"
TUNEUP_NTSYNC_LOAD = "/etc/modules-load.d/allyhub-ntsync.conf"
TUNEUP_NTSYNC_RULE = "/etc/udev/rules.d/70-allyhub-ntsync.rules"

# CachyOS-style memory settings. Swap ones only make sense with zram (fast swap), so they go with it.
MEM_SYSCTLS = {"vm.vfs_cache_pressure": "50", "vm.dirty_bytes": "268435456",
               "vm.dirty_background_bytes": "67108864", "vm.compaction_proactiveness": "0"}
ZRAM_SYSCTLS = {"vm.swappiness": "100", "vm.page-cluster": "0"}
SPLIT_LOCK_SYSCTLS = {"kernel.split_lock_mitigate": "0"}
# Setting dirty_*bytes zeroes the matching ratio, and the kernel refuses 0 for *_bytes, so Undo restores
# the ratios instead (which zeroes the bytes again).
DIRTY_RATIOS = ("vm.dirty_ratio", "vm.dirty_background_ratio")
ZRAM_MARKER = "/run/allyhub-zram"           # only the zram swap Ally Hub started is ever stopped
THP_SETTINGS = {"enabled": "always", "defrag": "defer+madvise"}
TUNEUP_KEYS = ("zram", "memory", "hugepages", "splitlock", "ntsync")
TUNEUP_TEXT = {
    "zram": ("Compressed swap in RAM",
             "Swaps to fast compressed memory instead of the slow swap file, so big games hitch less "
             "when memory fills up."),
    "memory": ("Memory tuning",
               "Keeps more game files cached and writes to storage in small steady bursts instead of big "
               "stalls."),
    "hugepages": ("Huge pages", "Lets games use bigger memory pages. A Steam Deck favorite from CryoUtilities."),
    "splitlock": ("No split-lock slowdown",
                  "Stops the kernel from deliberately slowing games that trip a split lock, which some "
                  "Windows games do."),
    "ntsync": ("NTSync", "Turns on the kernel's Windows-style sync driver so Proton can use it."),
}


# ---------- small readers ----------

def sysctl_file(key: str) -> Path:
    return SYSCTL_ROOT / key.replace(".", "/")


def sysctl_get(key: str) -> Optional[str]:
    p = sysctl_file(key)
    return read_text(p) if p.exists() else None


def thp_get(name: str) -> Optional[str]:
    """The selected value of a transparent_hugepage option ("always [madvise] never" -> "madvise")."""
    text = read_text(THP_ROOT / name)
    m = re.search(r"\[([^\]]+)\]", text)
    return m.group(1) if m else (text or None)


def thp_choices(name: str) -> list:
    return read_text(THP_ROOT / name).replace("[", "").replace("]", "").split()


def kernel_module_exists(name: str) -> bool:
    if Path(f"/sys/module/{name}").exists():
        return True
    dep = read_text(MODULES_ROOT / os.uname().release / "modules.dep")
    return bool(re.search(rf"/{re.escape(name)}\.ko(\.[a-z]+)?:", dep))


def ram_bytes() -> int:
    m = re.search(r"MemTotal:\s+(\d+)", read_text(MEMINFO))
    return int(m.group(1)) * 1024 if m else 0


def zram_supported() -> bool:
    return Path("/sys/block/zram0").exists() or kernel_module_exists("zram")


ZRAM_GENERATOR_CONFIGS = ("/etc/systemd/zram-generator.conf", "/usr/lib/systemd/zram-generator.conf")


def zram_system_managed() -> bool:
    """SteamOS (or zram-generator) already runs its own zram: leave it alone, just tune the swap settings."""
    return any(Path(p).exists() for p in ZRAM_GENERATOR_CONFIGS) or \
        (zram_active() and not Path(TUNEUP_ZRAM_UNIT).exists())


def zram_active() -> bool:
    return any(line.startswith("/dev/zram") for line in read_text(PROC_SWAPS).splitlines())


def ntsync_supported() -> bool:
    return NTSYNC_DEV.exists() or kernel_module_exists("ntsync")


def ntsync_ready() -> bool:
    return NTSYNC_DEV.exists() and os.access(NTSYNC_DEV, os.R_OK | os.W_OK)


# ---------- Game Boost ----------

def epp_files() -> list:
    return sorted(CPUFREQ_ROOT.glob("policy*/energy_performance_preference"))


def epp_current() -> Optional[str]:
    files = epp_files()
    return (read_text(files[0]) or None) if files else None


def epp_choices() -> list:
    files = epp_files()
    return read_text(files[0].parent / "energy_performance_available_preferences").split() if files else []


def epp_writable() -> bool:
    files = epp_files()
    return bool(files) and all(os.access(f, os.W_OK) for f in files)


def ppd_available() -> bool:
    """power-profiles-daemon: if SteamOS runs it, Game Boost asks it instead of writing the CPU directly,
    so the two never fight."""
    return bool(shutil.which("powerprofilesctl")) and service_active("power-profiles-daemon")


_BACKEND_CACHE = {"at": 0.0, "value": ""}


def boost_backend() -> str:
    """Cached for a minute: the agent asks every few seconds during a game, and the answer rarely changes."""
    now = time.monotonic()
    if now - _BACKEND_CACHE["at"] > 60 or not _BACKEND_CACHE["at"]:
        _BACKEND_CACHE["value"] = "ppd" if ppd_available() else "epp" if epp_files() else ""
        _BACKEND_CACHE["at"] = now
    return _BACKEND_CACHE["value"]


def boost_target(backend: str, on_battery: bool) -> Optional[str]:
    """What Game Boost asks for. Plugged in: full performance. On battery: a strong lean toward performance
    (EPP balance_performance) without burning the last few watts. power-profiles-daemon has no middle
    step, so on battery it's left alone."""
    if backend == "ppd":
        return None if on_battery else "performance"
    if backend == "epp":
        want = "balance_performance" if on_battery else "performance"
        choices = epp_choices()
        return want if not choices or want in choices else None
    return None


def boost_current(backend: str) -> Optional[str]:
    if backend == "ppd":
        rc, out = run_quiet(["powerprofilesctl", "get"])
        return (out.strip() or None) if rc == 0 else None
    return epp_current() if backend == "epp" else None


def _boost_set(backend: str, value: str) -> bool:
    if backend == "ppd":
        return run_quiet(["powerprofilesctl", "set", value])[0] == 0
    ok = False
    for f in epp_files():
        try:
            f.write_text(value)
            ok = True
        except OSError:
            pass        # EBUSY while the governor is "performance": that already is full speed
    return ok


def boost_apply(on_battery: bool) -> Optional[dict]:
    """Switch to the boost setting. Returns what to undo later, or None when nothing changed."""
    backend = boost_backend()
    target = boost_target(backend, on_battery)
    if not target:
        return None
    before = boost_current(backend)
    if not before or before == target:
        return None
    if not _boost_set(backend, target):
        return None
    return {"backend": backend, "before": before, "set": target, "at": time.time()}


def boost_restore(rec: dict) -> bool:
    """Put back what was there before, unless something else changed it meanwhile (then leave it alone:
    SteamOS or the user wins)."""
    if not rec or not rec.get("backend") or not rec.get("before"):
        return False
    if boost_current(rec["backend"]) != rec.get("set"):
        return False
    return _boost_set(rec["backend"], rec["before"])


def boost_ready() -> bool:
    b = boost_backend()
    return b == "ppd" or (b == "epp" and epp_writable())


def boost_permission_cmd() -> Optional[str]:
    """One password prompt so the agent can change the CPU's energy preference while a game runs.
    tmpfiles keeps it across reboots; chgrp/chmod make it work right away."""
    if not epp_files():
        return None
    try:
        import grp
        group = grp.getgrgid(os.getgid()).gr_name
    except (ImportError, KeyError):
        group = USER
    pattern = f"{CPUFREQ_ROOT}/policy*/energy_performance_preference"
    rule = f"z {pattern} 0664 root {group} - -"
    parts = [f"printf '%s\\n' {shlex.quote(rule)} | tee {BOOST_TMPFILES} >/dev/null",
             f"chgrp {shlex.quote(group)} {pattern}", f"chmod 0664 {pattern}"]
    return ("sudo sh -c " + shlex.quote(" && ".join(parts)) +
            " && echo 'Game Boost can now switch the CPU without a password.'")


# ---------- Tune-up ----------

def tuneup_plan() -> dict:
    """What this kernel supports: {"zram": bool, "memory": bool, ...}."""
    return {
        "zram": zram_supported(),
        "memory": all(sysctl_file(k).exists() for k in ("vm.vfs_cache_pressure", "vm.dirty_bytes")),
        "hugepages": (THP_ROOT / "enabled").exists() and "always" in thp_choices("enabled"),
        "splitlock": sysctl_file("kernel.split_lock_mitigate").exists(),
        "ntsync": ntsync_supported(),
    }


def tuneup_sysctls(plan: dict = None) -> dict:
    plan = tuneup_plan() if plan is None else plan
    out = {}
    if plan.get("memory"):
        out.update({k: v for k, v in MEM_SYSCTLS.items() if sysctl_file(k).exists()})
    if plan.get("splitlock"):
        out.update(SPLIT_LOCK_SYSCTLS)
    return out


def tuneup_thp(plan: dict = None) -> dict:
    plan = tuneup_plan() if plan is None else plan
    if not plan.get("hugepages"):
        return {}
    return {k: v for k, v in THP_SETTINGS.items() if v in thp_choices(k)}


def tuneup_applied() -> bool:
    """Any tune-up file counts, so a half-finished apply still offers Undo."""
    return any(Path(p).exists() for p in (TUNEUP_SYSCTL, TUNEUP_SWAP_SYSCTL, TUNEUP_ZRAM_UNIT, TUNEUP_TMPFILES,
                                          TUNEUP_NTSYNC_LOAD))


def tuneup_items() -> list:
    """Live status of each tweak: state is "on", "off" or "na" (this kernel can't)."""
    plan = tuneup_plan()
    sysctls = tuneup_sysctls(plan)
    live = {
        "zram": zram_active(),
        "memory": all(sysctl_get(k) == v for k, v in sysctls.items() if k in MEM_SYSCTLS),
        "hugepages": thp_get("enabled") == "always",
        "splitlock": sysctl_get("kernel.split_lock_mitigate") == "0",
        "ntsync": ntsync_ready(),
    }
    out = []
    for key in TUNEUP_KEYS:
        title, desc = TUNEUP_TEXT[key]
        state = "na" if not plan[key] else "on" if live[key] else "off"
        out.append({"key": key, "title": title, "desc": desc, "state": state})
    return out


def tuneup_snapshot() -> dict:
    """Current values of everything the tune-up changes, so Undo can put them back without a reboot."""
    keys = sorted(set(MEM_SYSCTLS) | set(ZRAM_SYSCTLS) | set(SPLIT_LOCK_SYSCTLS) | set(DIRTY_RATIOS))
    return {"sysctl": {k: sysctl_get(k) for k in keys if sysctl_get(k) is not None},
            "thp": {k: thp_get(k) for k in THP_SETTINGS if thp_get(k)},
            "at": time.time()}


def zram_script(size_bytes: int) -> str:
    return f"""#!/bin/sh
# Ally Hub: compressed swap in RAM (zram), like Bazzite and CachyOS. Undo from Tools > Performance.
case "$1" in
start)
  grep -q '^/dev/zram' /proc/swaps && exit 0
  modprobe zram 2>/dev/null
  [ -e /sys/block/zram0 ] || exit 0
  [ "$(cat /sys/block/zram0/disksize)" = 0 ] || exit 0
  echo zstd > /sys/block/zram0/comp_algorithm 2>/dev/null || echo lz4 > /sys/block/zram0/comp_algorithm 2>/dev/null
  echo {int(size_bytes)} > /sys/block/zram0/disksize && mkswap /dev/zram0 >/dev/null && swapon -p 100 /dev/zram0 \\
    && touch {ZRAM_MARKER}
  ;;
stop)
  [ -e {ZRAM_MARKER} ] || exit 0
  grep -q '^/dev/zram0 ' /proc/swaps && swapoff /dev/zram0
  echo 1 > /sys/block/zram0/reset 2>/dev/null
  rm -f {ZRAM_MARKER}
  true
  ;;
esac
"""


ZRAM_UNIT_TEXT = f"""[Unit]
Description=Ally Hub compressed swap in RAM (zram)
After=systemd-modules-load.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart={TUNEUP_ZRAM_SCRIPT} start
ExecStop={TUNEUP_ZRAM_SCRIPT} stop

[Install]
WantedBy=multi-user.target
"""


def _tee(body: str, path: str) -> str:
    return f"printf '%s' {shlex.quote(body)} | tee {path} >/dev/null"


def tuneup_apply_cmd(plan: dict = None) -> Optional[str]:
    plan = tuneup_plan() if plan is None else plan
    sysctls = tuneup_sysctls(plan)
    thp = tuneup_thp(plan)
    if not (sysctls or thp or plan.get("zram") or plan.get("ntsync")):
        return None
    parts = []
    if plan.get("zram") and zram_system_managed():
        swap = "".join(f"{k} = {v}\n" for k, v in ZRAM_SYSCTLS.items() if sysctl_file(k).exists())
        parts += [f"{{ ! grep -q '^/dev/zram' /proc/swaps || {{ "
                  f"{_tee('# Ally Hub tune-up: swap settings for zram' + chr(10) + swap, TUNEUP_SWAP_SYSCTL)}"
                  f" && sysctl -q -e -p {TUNEUP_SWAP_SYSCTL}; }} || true; }}"]
    elif plan.get("zram"):
        size = max(ram_bytes() // 2, 1 << 30) // (1 << 20) * (1 << 20)     # half the RAM, at least 1 GB
        swap = "".join(f"{k} = {v}\n" for k, v in ZRAM_SYSCTLS.items() if sysctl_file(k).exists())
        parts += ["mkdir -p /etc/allyhub", _tee(zram_script(size), TUNEUP_ZRAM_SCRIPT),
                  f"chmod 0755 {TUNEUP_ZRAM_SCRIPT}", _tee(ZRAM_UNIT_TEXT, TUNEUP_ZRAM_UNIT),
                  "systemctl daemon-reload",
                  "{ systemctl enable --now allyhub-zram.service || echo 'Compressed swap could not start.'; }",
                  # swap tuning suits fast zram, not the swap file: only when zram really came up
                  f"{{ ! grep -q '^/dev/zram' /proc/swaps || {{ "
                  f"{_tee('# Ally Hub tune-up: swap settings for zram' + chr(10) + swap, TUNEUP_SWAP_SYSCTL)}"
                  f" && sysctl -q -e -p {TUNEUP_SWAP_SYSCTL}; }} || true; }}"]
    body = "# Ally Hub tune-up (Tools > Performance). Undo there, or delete this file.\n"
    body += "".join(f"{k} = {v}\n" for k, v in sysctls.items())
    parts += [_tee(body, TUNEUP_SYSCTL), f"{{ sysctl -q -e -p {TUNEUP_SYSCTL} || true; }}"]
    if thp:
        lines = "".join(f"w {THP_ROOT}/{k} - - - - {v}\n" for k, v in thp.items())
        parts += [_tee("# Ally Hub tune-up: huge pages\n" + lines, TUNEUP_TMPFILES),
                  f"{{ systemd-tmpfiles --create {TUNEUP_TMPFILES} || true; }}"]
    if plan.get("ntsync"):
        parts += [_tee("ntsync\n", TUNEUP_NTSYNC_LOAD),
                  _tee('KERNEL=="ntsync", MODE="0666"\n', TUNEUP_NTSYNC_RULE),
                  "udevadm control --reload",
                  f"{{ modprobe ntsync 2>/dev/null; chmod 0666 {NTSYNC_DEV} 2>/dev/null; true; }}"]
    return "sudo sh -c " + shlex.quote(" && ".join(parts)) + " && echo 'Tune-up applied.'"


def tuneup_undo_cmd(before: dict = None) -> str:
    before = before or {}
    parts = ["{ systemctl disable --now allyhub-zram.service 2>/dev/null; true; }",
             f"rm -f {TUNEUP_ZRAM_UNIT} {TUNEUP_ZRAM_SCRIPT} {TUNEUP_SYSCTL} {TUNEUP_SWAP_SYSCTL} {TUNEUP_TMPFILES} "
             f"{TUNEUP_NTSYNC_LOAD} {TUNEUP_NTSYNC_RULE}",
             "{ rmdir /etc/allyhub 2>/dev/null; true; }",
             "{ systemctl daemon-reload || true; }", "{ udevadm control --reload || true; }"]
    saved = before.get("sysctl") or {}
    order = [k for k in saved if k not in DIRTY_RATIOS] + [k for k in DIRTY_RATIOS if k in saved]
    restore = [f"sysctl -q -w {shlex.quote(f'{k}={saved[k]}')}" for k in order
               if re.fullmatch(r"[a-z0-9_.-]+", k) and re.fullmatch(r"[0-9]+", str(saved[k]))
               and not (k.endswith("_bytes") and str(saved[k]) == "0")]
    restore += [f"echo {shlex.quote(v)} > {THP_ROOT}/{k}" for k, v in (before.get("thp") or {}).items()
                if k in THP_SETTINGS and re.fullmatch(r"[a-z+]+", str(v))]
    if not restore:
        restore = ["sysctl -q --system"]      # no snapshot: reload SteamOS's own values
    parts.append("{ " + "; ".join(restore) + "; true; }")
    return "sudo sh -c " + shlex.quote(" && ".join(parts)) + " && echo 'Tune-up removed.'"


# ---------- Every-game settings: Proton options set once for all games ----------
# Bazzite-style: a systemd environment.d file, which SteamOS's Game Mode (a systemd user session) passes to
# Steam and every game. No launch options, no password. Takes effect after a restart; `game_env_live`
# reads Steam's real environment to show whether it did. Researched Oct 2026: GE-Proton and Proton-CachyOS
# both use PROTON_FSR4_UPGRADE (RDNA3/3.5 included, default FSR 4.1.1); the RDNA3-specific
# variable some guides mention does nothing. Valve's Proton 11 ships AMD's FSR 4 file itself, so these are harmless there.

GAME_ENV_FILE = HOME / ".config/environment.d/90-allyhub-games.conf"
COMPAT_TOOL_DIRS = (HOME / ".steam/root/compatibilitytools.d", STEAM_ROOT / "compatibilitytools.d")
GAME_ENV_OPTIONS = {     # key -> (variables, title, description)
    "fsr4": ({"PROTON_FSR4_UPGRADE": "1"}, "FSR 4 upgrade",
             "Games with FSR 3.1 use AMD's sharper FSR 4 instead (version 4.1.1, which supports the Ally's "
             "GPU). It looks much better but costs some frames on a handheld, so pair it with FSR's "
             "Balanced or Performance mode. Needs GE-Proton or Proton-CachyOS."),
    "fsr4_badge": ({"PROTON_FSR4_INDICATOR": "1"}, "Show the FSR 4 badge",
                   "Puts a small FSR label in the corner of the game, so you can see it's working."),
}


def game_env_read() -> dict:
    out = {}
    for line in read_text(GAME_ENV_FILE).splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def game_env_enabled(opt: str) -> bool:
    cur = game_env_read()
    return all(cur.get(k) == v for k, v in GAME_ENV_OPTIONS[opt][0].items())


def game_env_set(opt: str, on: bool) -> None:
    cur = game_env_read()
    for k, v in GAME_ENV_OPTIONS[opt][0].items():
        if on:
            cur[k] = v
        else:
            cur.pop(k, None)
    if not cur:
        GAME_ENV_FILE.unlink(missing_ok=True)
        return
    GAME_ENV_FILE.parent.mkdir(parents=True, exist_ok=True)
    body = "# Ally Hub: settings for every game (Tools > Performance). Applied after a restart.\n"
    GAME_ENV_FILE.write_text(body + "".join(f"{k}={v}\n" for k, v in sorted(cur.items())))


def process_env(names: tuple = ("steam",)) -> Optional[dict]:
    """Environment of the user's running process with one of these names (Steam by default), or None."""
    uid = os.getuid()
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return None
    for pid in pids:
        try:
            if os.stat(f"/proc/{pid}").st_uid != uid or read_text(f"/proc/{pid}/comm") not in names:
                continue
            raw = Path(f"/proc/{pid}/environ").read_bytes()
        except OSError:
            continue
        return dict(kv.split("=", 1) for kv in raw.decode("utf-8", "replace").split("\0") if "=" in kv)
    return None


def game_env_live(opt: str, env: Optional[dict] = None) -> Optional[bool]:
    """True when Steam already runs with the option, False when not yet, None when Steam isn't running."""
    env = process_env() if env is None else env
    if env is None:
        return None
    return all(env.get(k) == v for k, v in GAME_ENV_OPTIONS[opt][0].items())


def custom_protons() -> list:
    """Installed Proton builds that understand the FSR 4 option (GE-Proton, Proton-CachyOS, Proton-EM)."""
    found = set()
    for d in COMPAT_TOOL_DIRS:
        try:
            found.update(p.name for p in d.iterdir()
                         if p.is_dir() and re.search(r"(?i)ge-proton|cachyos|proton-em|proton.*-em", p.name))
        except OSError:
            pass
    return sorted(found)


def performance_summary() -> str:
    """One line for reports and Ally Doctor."""
    cfg = load_config().get("performance") or {}
    on = [i["key"] for i in tuneup_items() if i["state"] == "on"]
    return (f"boost={'on' if cfg.get('boost') else 'off'}({boost_backend() or 'none'}) "
            f"tuneup={'applied' if tuneup_applied() else 'off'}[{','.join(on)}] "
            f"games={','.join(sorted(game_env_read())) or 'none'}")


# ==========================================================================
# GitHub: auto-update and error reporting
# ==========================================================================

TOKEN_FILE = DATA_DIR / "github_token"
UPDATE_STATE = DATA_DIR / "update_state.json"
REPORT_DIR = DATA_DIR / "reports"
REPORT_SENT = DATA_DIR / "reports_sent.json"
PREV_DIR = DATA_DIR / "previous"
APP_LOG = DATA_DIR / "allyhub.log"
APP_FILES = ("allyhub.py", "core.py", "agent.py", "gui.py", "allyhub.svg", "install.sh",
             "uninstall.sh", "README.md", "CHANGELOG.md", "VERSION")
REQUIRED_FILES = ("allyhub.py", "core.py", "agent.py", "gui.py", "VERSION")
# Where a file can sit: the repo keeps its files in folders (app/, scripts/, docs/), the install on the
# device is flat.
REPO_DIRS = ("app", "scripts", "docs", "")


def repo_file(root: Path, name: str) -> Path:
    for d in REPO_DIRS:
        p = root / d / name if d else root / name
        if p.exists():
            return p
    return root / name
MAX_REPORTS_PER_DAY = 25
REPORT_REPEAT_S = 6 * 3600       # same problem on the same version: once per 6 hours
ATTACH_MAX = 60000              # GitHub allows 65536 characters per comment
JOB_LOG_DIR = DATA_DIR / "jobs"
HEALTHY_AFTER_S = 45
UPDATE_INTERVAL_S = 6 * 3600     # how often devices look for a new version
MAX_UNHEALTHY_BOOTS = 3


def app_log(component: str, msg: str) -> None:
    """Small rotating log that gets attached (scrubbed) to error reports."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if APP_LOG.exists() and APP_LOG.stat().st_size > 256 * 1024:
            os.replace(APP_LOG, APP_LOG.with_suffix(".log.1"))
        with open(APP_LOG, "a") as f:
            f.write(f"{time.strftime('%m-%d %H:%M:%S')} [{component}] {msg}\n")
    except OSError:
        pass


def recent_log(lines: int = 40) -> str:
    try:
        return "".join(APP_LOG.read_text(errors="replace").splitlines(True)[-lines:])
    except OSError:
        return ""


def repo_name() -> str:
    return load_config()["updates"].get("repo") or REPO_DEFAULT


def github_token() -> Optional[str]:
    t = read_text(TOKEN_FILE)
    return t or None


def save_github_token(token: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = TOKEN_FILE.with_suffix(".tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)     # private from the first byte
    with os.fdopen(fd, "w") as f:
        f.write(token.strip())
    os.replace(tmp, TOKEN_FILE)


def secure_data_dir() -> None:
    """Logs, job output, reports and backups are only for this user (other accounts on the device can't read
    them)."""
    for d in (DATA_DIR, CONFIG_DIR):
        try:
            if d.exists() and stat.S_IMODE(d.stat().st_mode) & 0o077:
                d.chmod(0o700)
        except OSError:
            pass


def gh_request(method: str, path: str, data: dict = None, accept: str = "application/vnd.github+json",
               timeout: int = 25, auth: bool = True) -> tuple:
    """Returns (status, body_bytes). status 0 means a network error."""
    url = path if path.startswith("http") else "https://api.github.com" + path
    headers = {"Accept": accept, "User-Agent": f"AllyHub/{VERSION}",
               "X-GitHub-Api-Version": "2022-11-28"}
    tok = github_token() if auth else None
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    body = json.dumps(data).encode() if data is not None else None
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        if e.code == 401 and tok:
            # an expired or revoked access key mustn't stop updates: public reads work without one
            return gh_request(method, path, data, accept, timeout, auth=False)
        try:
            return e.code, e.read()
        except Exception:
            return e.code, b""
    except Exception:
        return 0, b""


# ---------- privacy scrubbing ----------

_SCRUB = [
    (re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"), "<token>"),
    (re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b"), "<mac>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<ip>"),
    (re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){3,7}[0-9a-fA-F]{1,4}\b"), "<ip6>"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    (re.compile(r"(?i)(pin|password|passwd|token|secret)(\s*[=:]\s*)\S+"), r"\1\2<hidden>"),
]


def scrub(text: str) -> str:
    if not text:
        return ""
    text = text.replace(str(HOME), "~")
    for rx, rep in _SCRUB:
        text = rx.sub(rep, text)
    if USER and len(USER) >= 3:
        text = re.sub(rf"\b{re.escape(USER)}\b", "<user>", text)
    pin = (load_config()["agent"].get("remote_pin") or "")
    if len(pin) >= 4:
        text = text.replace(pin, "<pin>")
    # Steam account ids point straight at a public Steam profile; hostnames are often a person's name
    text = re.sub(r"\b7656119\d{10}\b", "<steam-id>", text)
    try:
        id3 = steam_user_id3()
    except Exception:
        id3 = None
    if id3 and len(id3) >= 5:
        text = re.sub(rf"\b{re.escape(id3)}\b", "<steam-id>", text)
    host = socket.gethostname()
    if host and len(host) >= 3 and host.lower() not in ("localhost", "steamdeck"):
        text = re.sub(rf"\b{re.escape(host)}\b", "<host>", text)      # exact case: "ally" mustn't eat "Ally Hub"
    return text


# ---------- reports ----------

def _fingerprint(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:10]


def environment_summary() -> str:
    osr = os_release()
    return (f"- Ally Hub: {version_label()} (build {VERSION})\n- SteamOS: {osr.get('VERSION_ID', '?')} "
            f"(build {osr.get('BUILD_ID', '?')})\n- Kernel: {os.uname().release}\n"
            f"- Device: {device_name()}\n- Mode: {'Game Mode' if in_game_mode() else 'Desktop'}\n"
            f"- Python: {'.'.join(map(str, __import__('sys').version_info[:3]))}")


# Why the last queue_report() call did or didn't queue: "queued", "off", "no_key",
# "duplicate" (same problem already reported in the last day) or "limit" (daily cap).
LAST_QUEUE = ""


def job_log_path(key: str) -> Path:
    return JOB_LOG_DIR / (re.sub(r"[^A-Za-z0-9._-]+", "_", key or "job")[:60] + ".log")


def job_log_tail(key: str, chars: int = 40000) -> str:
    return read_text(job_log_path(key))[-chars:]


def _redacted_config() -> dict:
    cfg = json.loads(json.dumps(load_config()))
    cfg.get("agent", {}).pop("remote_pin", None)
    cfg.get("wol", {}).pop("mac", None)
    return cfg


def diagnostics_snapshot() -> str:
    """Everything worth knowing when something breaks, in one block (scrubbed later with the report).
    Each probe is guarded: a broken probe must never stop a report."""
    def probe(name, fn):
        try:
            return f"{name}: {fn()}"
        except Exception as e:
            return f"{name}: (probe failed: {type(e).__name__})"
    lines = [
        probe("Disk free", lambda: disk_usage(str(HOME))),
        probe("Battery", lambda: battery_percent()),
        probe("Agent", lambda: ("running" if agent_running() else "stopped") + f", state {agent_state()}"),
        probe("Update state", lambda: {k: v for k, v in update_state().items() if k != "history"}),
        probe("Decky", lambda: ("running" if service_active("plugin_loader") else "not running") +
              "; plugins " + ", ".join(f"{i['name']} {i['version']}" for i in installed_decky_plugins().values())),
        probe("Steam account folder", lambda: steam_user_id3() or "not found"),
        probe("Steam debugger (Decky/CEF)", lambda: "on" if cef_eval("1+1", timeout=3) == 2 else "off"),
        probe("Proton builds", lambda: ", ".join(custom_protons()) or "only Valve's"),
        probe("Performance", performance_summary),
        probe("Lighting", lambda: {k: v for k, v in (load_config().get("lighting") or {}).items()
                                   if k in ("controller", "encoding", "hid_method", "effect")}),
        probe("NonSteamLaunchers", lambda: "installed: " + (", ".join(n for n in NSL_STORES if nsl_installed(n))
                                                             or "none") +
              f"; scanner service {'active' if service_active('nslgamescanner', user=True) else 'inactive'}"),
        probe("Config", lambda: json.dumps(_redacted_config(), sort_keys=True)),
    ]
    rc, journal = run_quiet(["journalctl", "--user", "-u", "allyhub-agent", "-n", "40", "--no-pager"], timeout=8)
    if journal:
        lines += ["", "--- agent journal ---", journal]
    return "\n".join(lines)


_UPLOAD_LOCK = None


def upload_soon():
    """Send queued reports right away on a background thread (GUI or agent), never blocking the caller."""
    import threading
    global _UPLOAD_LOCK
    if _UPLOAD_LOCK is None:
        _UPLOAD_LOCK = threading.Lock()
    if not github_token():
        return

    def run():
        if _UPLOAD_LOCK.acquire(blocking=False):
            try:
                upload_reports()
            except Exception:
                pass
            finally:
                _UPLOAD_LOCK.release()
    threading.Thread(target=run, daemon=True).start()


def queue_report(kind: str, title: str, details: str, fingerprint: str = None, attachments: list = None,
                 force: bool = False, upload: bool = True) -> Optional[Path]:
    """Save a scrubbed report and send it straight away. `attachments` are (name, text) pairs posted as
    follow-up comments so nothing gets cut short. A system snapshot is always attached. `force` is for
    reports the user sends by hand (they still need the access key)."""
    global LAST_QUEUE
    cfg = load_config()
    if not cfg["updates"].get("reporting") and not force:
        LAST_QUEUE = "off"
        return None
    fp = fingerprint or _fingerprint(kind, title)
    key = f"{fp}@{VERSION}"                           # a new version may not have fixed it: report again
    sent = read_json(REPORT_SENT, {}) or {}
    now = time.time()
    if not force and now - sent.get(key, 0) < REPORT_REPEAT_S:
        LAST_QUEUE = "duplicate"
        return None
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    if not force and any(fp in p.name for p in REPORT_DIR.glob("*.json")):
        LAST_QUEUE = "duplicate"                      # already waiting to be sent
        return None
    today = [p for p in REPORT_DIR.glob("*.json") if now - p.stat().st_mtime < 86400]
    if len(today) >= MAX_REPORTS_PER_DAY:
        LAST_QUEUE = "limit"
        return None
    LAST_QUEUE = "queued" if github_token() else "no_key"
    atts = [(n, t) for n, t in (attachments or []) if t and t.strip()]
    atts.append(("System snapshot", diagnostics_snapshot()))
    atts.append(("Ally Hub log (last 300 lines)", recent_log(300)))
    report = {
        "kind": kind, "fingerprint": fp, "version": VERSION, "time": time.strftime("%Y-%m-%d %H:%M"),
        "channel": update_channel(),
        "title": scrub(title)[:120],
        "body": (f"**Kind:** {kind}\n**Fingerprint:** `{fp}`\n\n### Environment\n{environment_summary()}\n\n"
                 f"### Details\n```\n{scrub(details)[-20000:]}\n```\n\n"
                 f"### Recent log\n```\n{scrub(recent_log(60))[-8000:]}\n```\n"
                 + (f"\n_Attached below: {', '.join(n for n, _ in atts)}._\n" if atts else "")),
        "attachments": [{"name": n, "text": scrub(t)[-ATTACH_MAX:]} for n, t in atts],
    }
    path = REPORT_DIR / f"{int(now)}-{fp}.json"
    write_json(path, report)
    app_log("report", f"queued {kind}: {title[:80]}")
    if upload and LAST_QUEUE == "queued":
        upload_soon()
    return path


def user_report(text: str, page: str = "") -> Optional[Path]:
    """The "Report a problem" button: the user's words plus everything needed to act on them."""
    atts = []
    jobs = sorted(JOB_LOG_DIR.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)[:3] \
        if JOB_LOG_DIR.exists() else []
    for j in jobs:
        atts.append((f"Job output: {j.stem} ({time.strftime('%H:%M', time.localtime(j.stat().st_mtime))})",
                     read_text(j)[-ATTACH_MAX:]))
    if NSL_LOG.exists() and time.time() - NSL_LOG.stat().st_mtime < 86400:
        atts.append(("NonSteamLaunchers log", nsl_log_tail(400)))
    return queue_report("user", (text.strip() or "Problem reported from Ally Hub")[:110],
                        f"Reported by hand{f' on the {page} page' if page else ''}:\n\n{text.strip()}",
                        _fingerprint("user", str(time.time())), attachments=atts, force=True)


def report_update_failure(msg: str) -> Optional[Path]:
    """An update that didn't install is a problem to fix, unless it's just the network."""
    if not msg or "HTTP 0" in msg or "Couldn't reach" in msg:
        return None
    return queue_report("update-failure", f"Update didn't install: {msg[:90]}", msg,
                        _fingerprint("update", re.sub(r"\d+", "N", msg)[:60]))


def _comment_chunks(name: str, text: str) -> list:
    out, size = [], 60000
    parts = [text[i:i + size] for i in range(0, len(text), size)] or [""]
    for n, part in enumerate(parts):
        label = name + (f" (part {n + 1} of {len(parts)})" if len(parts) > 1 else "")
        out.append(f"<details><summary>{label}</summary>\n\n```\n{part}\n```\n</details>")
    return out


def report_hint() -> str:
    """Plain-language reason the last report wasn't sent, for messages to the user."""
    return {
        "off": "Turn on error reports (Settings → General) to have problems like this fixed automatically.",
        "no_key": "Error reports are on, but there's no GitHub access key yet. Add one on Settings → General.",
        "duplicate": "This exact problem was already reported in the last day, so it wasn't sent again. "
                     "A fix may already be out: Settings → General → Check now.",
        "limit": "Ally Hub already sent its daily maximum of reports. It'll send more tomorrow.",
    }.get(LAST_QUEUE, "")


def report_exception(component: str, exc_info=None) -> Optional[Path]:
    import sys as _sys
    etype, evalue, tb = exc_info or _sys.exc_info()
    if etype is None or issubclass(etype, (KeyboardInterrupt, SystemExit)):
        return None          # closing the app (Ctrl+C, Game Mode exit) isn't a crash
    frames = traceback.extract_tb(tb)
    last = frames[-1] if frames else None
    where = f"{Path(last.filename).name}:{last.name}" if last else "?"
    text = "".join(traceback.format_exception(etype, evalue, tb))
    app_log(component, f"exception {etype.__name__} in {where}: {evalue}")
    return queue_report("crash", f"{component}: {etype.__name__} in {where}: {evalue}", text,
                        _fingerprint("crash", component, etype.__name__, where))


def pending_reports() -> list:
    return sorted(REPORT_DIR.glob("*.json")) if REPORT_DIR.exists() else []


def upload_reports() -> tuple:
    """Send queued reports as GitHub issues. Returns (sent, failed)."""
    cfg = load_config()
    if not github_token():
        return 0, 0
    files = pending_reports()
    if not cfg["updates"].get("reporting"):          # automatic reports off: only ones sent by hand
        files = [f for f in files if (read_json(f) or {}).get("kind") == "user"]
    if not files:
        return 0, 0
    lock = open(REPORT_DIR / ".upload.lock", "w")        # GUI and agent may both try: one at a time
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return 0, 0
    try:
        return _upload_locked(pending_reports())
    finally:
        lock.close()


def _upload_locked(files: list) -> tuple:
    if not files:
        return 0, 0
    repo = repo_name()
    status, body = gh_request("GET", f"/repos/{repo}/issues?state=open&per_page=100&labels=auto-report")
    open_issues = json.loads(body) if status == 200 else []
    sent_ok, failed = 0, 0
    sent = read_json(REPORT_SENT, {}) or {}
    for f in files:
        rep = read_json(f)
        if not rep:
            f.unlink(missing_ok=True)
            continue
        fp = rep["fingerprint"]
        existing = next((i for i in open_issues if fp in (i.get("title") or "")), None)
        number = None
        if existing:
            number = existing["number"]
            status, _ = gh_request("POST", f"/repos/{repo}/issues/{number}/comments",
                                   {"body": f"Happened again on {rep['time']} "
                                            f"(v{display_version(rep['version'])}).\n\n" + rep["body"][:60000]})
        else:
            prefix = "[report]" if rep["kind"] == "user" else "[auto]"
            payload = {"title": f"{prefix} {rep['title']} ({fp})", "body": rep["body"][:65000],
                       "labels": ["auto-report", rep["kind"]] + (["testing"] if rep.get("channel") == "testing" else [])}
            status, resp = gh_request("POST", f"/repos/{repo}/issues", payload)
            if status == 422:   # labels not allowed for this key: send without them
                payload.pop("labels")
                status, resp = gh_request("POST", f"/repos/{repo}/issues", payload)
            try:
                number = json.loads(resp).get("number") if status in (200, 201) else None
            except (ValueError, AttributeError):
                number = None
        if status in (200, 201):
            for att in rep.get("attachments") or []:
                if number:
                    for chunk in _comment_chunks(att.get("name", "Attachment"), att.get("text", "")):
                        gh_request("POST", f"/repos/{repo}/issues/{number}/comments", {"body": chunk})
            sent[f"{fp}@{rep.get('version', '')}"] = time.time()
            f.unlink(missing_ok=True)
            sent_ok += 1
        else:
            failed += 1
            app_log("report", f"upload failed with HTTP {status}")
            if status in (401, 403, 404):
                break
    week_ago = time.time() - 7 * 86400
    write_json(REPORT_SENT, {k: v for k, v in sent.items() if v > week_ago})
    return sent_ok, failed


# ---------- updates ----------

def parse_version(v: str) -> tuple:
    """Up to 4 parts: Stable is x.y.z, a test build is the Stable version plus a revision (x.y.z.r)."""
    return tuple(int(x) for x in re.findall(r"\d+", v or "0")[:4]) or (0,)


VERSION_RE = r"\d+\.\d+\.\d+(?:\.\d+)?"      # 6.3.6 (Stable) or 6.3.6.4 (test build, revision 4)
MAX_TEST_REVISIONS = 10                         # the owner: more than that before Stable means it's not focused


def plugin_newer(latest: str, installed: str) -> bool:
    """True only when the store's version is really newer, so the store never "updates" a newer build
    (like the GitHub release Ally Hub installs for frame generation) down to its older copy."""
    return parse_version(latest) > parse_version(installed)


# Public version numbers. The VERSION file is the updater's build number and must only ever go up,
# because installed copies update only to a HIGHER number. People see the build with 5 taken off the
# first part: build 6.0.0 = 1.0.0, 6.0.3 = 1.0.3, 6.1.0 = 1.1.0, 7.0.0 = 2.0.0. Lower builds are shown as is.
PUBLIC_VERSION_OFFSET = 5


def display_version(v: str = None) -> str:
    v = v or VERSION
    t = parse_version(v)
    if len(t) in (3, 4) and t[0] > PUBLIC_VERSION_OFFSET:
        return ".".join(str(x) for x in (t[0] - PUBLIC_VERSION_OFFSET,) + t[1:])
    return v


def update_state() -> dict:
    return read_json(UPDATE_STATE, {}) or {}


def save_update_state(st: dict) -> None:
    write_json(UPDATE_STATE, st)


# Update channels. Stable devices follow main. Testing devices follow whichever of main and the testing branch
# has the higher build, so a fix released on main never skips them. Testing builds always carry a higher
# number than the stable release they lead to.
UPDATE_CHANNELS = {"stable": ("main",), "testing": ("main", "testing")}


def update_channel(cfg: dict = None) -> str:
    c = ((cfg or load_config()).get("updates") or {}).get("channel")
    return c if c in UPDATE_CHANNELS else "stable"


def version_label(v: str = None) -> str:
    """The version people see, marked when this device is on test builds."""
    return display_version(v) + (" (testing)" if update_channel() == "testing" else "")


def remote_version(branch: str = "main") -> Optional[str]:
    status, body = gh_request("GET", f"/repos/{repo_name()}/contents/VERSION?ref={branch}",
                              accept="application/vnd.github.raw+json")
    if status == 200:
        v = body.decode(errors="replace").strip()
        return v if re.fullmatch(VERSION_RE, v) else None
    return None


def check_for_update() -> dict:
    """{'current', 'remote', 'branch', 'available', 'stable', 'error'}. 'stable' is main's version, so a device
    that left the testing channel can be offered the way back."""
    st = update_state()
    st["last_check"] = time.time()
    found = {b: remote_version(b) for b in UPDATE_CHANNELS[update_channel()]}
    best = max(((v, b) for b, v in found.items() if v), key=lambda t: parse_version(t[0]), default=(None, "main"))
    remote, branch = best
    out = {"current": VERSION, "remote": remote, "branch": branch, "available": False,
           "stable": found.get("main"), "error": None}
    if remote is None:
        out["error"] = "Couldn't reach GitHub"
    elif parse_version(remote) > parse_version(VERSION) and remote not in st.get("bad", []):
        out["available"] = True
    st["last_remote"] = remote
    save_update_state(st)
    return out


def install_update(expected: str, branch: str = "main", allow_older: bool = False) -> tuple:
    """Download a branch, verify it, back up the current version, install. (ok, message)
    allow_older is only for going back to stable after the testing channel: exactly `expected`, nothing else."""
    if branch not in {b for bs in UPDATE_CHANNELS.values() for b in bs}:
        return False, f"Unknown update branch {branch}"
    status, data = gh_request("GET", f"/repos/{repo_name()}/tarball/{branch}",
                              accept="application/vnd.github+json", timeout=90)
    if status != 200 or not data:
        return False, f"Download failed (HTTP {status})"
    with tempfile.TemporaryDirectory() as tmp:
        tpath = Path(tmp) / "src.tar.gz"
        tpath.write_bytes(data)
        try:
            with tarfile.open(tpath) as tar:
                try:
                    tar.extractall(Path(tmp) / "x", filter="data")
                except TypeError:
                    tar.extractall(Path(tmp) / "x")
        except (tarfile.TarError, OSError) as e:
            return False, f"Bad download: {e}"
        roots = [p for p in (Path(tmp) / "x").iterdir() if p.is_dir()]
        if len(roots) != 1:
            return False, "Unexpected download layout"
        src = roots[0]
        missing = [f for f in REQUIRED_FILES if not repo_file(src, f).exists()]
        if missing:
            return False, f"Update is missing {', '.join(missing)}"
        new_ver = read_text(repo_file(src, "VERSION"))
        # A newer release can land between the check and the download (two releases minutes apart, or
        # GitHub's short cache): take the newer one instead of failing. Never go backwards or to a bad one.
        if allow_older:
            if new_ver != expected or new_ver == VERSION:
                return False, f"Version mismatch ({new_ver} vs {expected})"
        elif not re.fullmatch(VERSION_RE, new_ver or "") or \
                parse_version(new_ver) < parse_version(expected) or \
                parse_version(new_ver) <= parse_version(VERSION) or new_ver in update_state().get("bad", []):
            return False, f"Version mismatch ({new_ver} vs {expected})"
        expected = new_ver
        import py_compile
        for f in ("allyhub.py", "core.py", "agent.py", "gui.py"):
            try:
                py_compile.compile(str(repo_file(src, f)), cfile=str(Path(tmp) / (f + "c")), doraise=True)
            except py_compile.PyCompileError as e:
                return False, f"Update has a syntax error in {f}: {e.msg[:200]}"
        if PREV_DIR.exists():
            shutil.rmtree(PREV_DIR)
        PREV_DIR.mkdir(parents=True)
        for f in APP_FILES:
            if (APP_DIR / f).exists():
                shutil.copy2(APP_DIR / f, PREV_DIR / f)
        (PREV_DIR / "VERSION").write_text(VERSION)
        for f in APP_FILES:
            if repo_file(src, f).exists():
                shutil.copy2(repo_file(src, f), APP_DIR / f)
        shutil.rmtree(APP_DIR / "__pycache__", ignore_errors=True)
    st = update_state()
    st.update({"pending": expected, "from": VERSION, "boots": {}, "healthy_by": [], "installed_at": time.time(),
               "branch": branch})
    st.setdefault("history", []).append({"from": VERSION, "to": expected, "at": time.time()})
    st["history"] = st["history"][-20:]
    save_update_state(st)
    app_log("update", f"installed {expected} (from {VERSION})")
    try:
        sync_testing_rescue()
    except Exception:
        pass
    return True, f"Updated to {display_version(expected)}"


def previous_version() -> Optional[str]:
    return read_text(PREV_DIR / "VERSION") or None if (PREV_DIR / "core.py").exists() else None


def rollback(reason: str, mark_bad: bool = True) -> tuple:
    prev = previous_version()
    if not prev:
        return False, "No previous version saved"
    bad_ver = read_text(APP_DIR / "VERSION") or VERSION
    for f in APP_FILES:
        if (PREV_DIR / f).exists():
            shutil.copy2(PREV_DIR / f, APP_DIR / f)
    shutil.rmtree(APP_DIR / "__pycache__", ignore_errors=True)
    st = update_state()
    if mark_bad:
        st.setdefault("bad", [])
        if bad_ver not in st["bad"]:
            st["bad"].append(bad_ver)
    st.pop("pending", None)
    st["rolled_back"] = {"from": bad_ver, "to": prev, "reason": reason, "at": time.time()}
    save_update_state(st)
    app_log("update", f"rolled back {bad_ver} -> {prev}: {reason}")
    queue_report("rollback", f"Update {bad_ver} rolled back: {reason}",
                 f"Rolled back from {bad_ver} to {prev}.\nReason: {reason}",
                 _fingerprint("rollback", bad_ver))
    return True, f"Rolled back to {prev}"


# Probation (1.4.1, the owner: "an automatic rollback for a number of failed starts"). Each part proves itself:
# the app window ("gui") and the background helper ("agent") count their own starts. 1.4.0 showed why: the helper
# started fine and ended probation for the whole update while the window crashed on every start, so nothing rolled
# back. Now the update stays on probation until the window has worked (and the helper too, when it's on), and
# MAX_UNHEALTHY_BOOTS failed starts of either part roll it back.

def _boots(st: dict) -> dict:
    b = st.get("boots")
    return dict(b) if isinstance(b, dict) else {}       # older versions saved one number for both parts


def startup_check(component: str) -> str:
    """Call at startup (the GUI only once it knows it's the only window). Returns 'ok', 'probation' or
    'rolled_back'."""
    st = update_state()
    if st.get("pending") != VERSION or component in (st.get("healthy_by") or []):
        return "ok"
    boots = _boots(st)
    boots[component] = boots.get(component, 0) + 1
    st["boots"] = boots
    save_update_state(st)
    if boots[component] > MAX_UNHEALTHY_BOOTS:
        what = "Ally Hub's window" if component == "gui" else "the background helper"
        ok, _msg = rollback(f"{what} failed to start {MAX_UNHEALTHY_BOOTS} times after updating")
        if ok and component != "agent":
            restart_agent_service()      # it may be running the bad version's code: back to the old one
        return "rolled_back" if ok else "probation"
    return "probation"


def restart_agent_service() -> None:
    """After a rollback from the GUI: the helper restarts on the restored files (only if it was running)."""
    run_quiet(["systemctl", "--user", "try-restart", "allyhub-agent.service"], timeout=20)


def mark_healthy(component: str) -> None:
    st = update_state()
    if st.get("pending") != VERSION:
        return
    hb = list(st.get("healthy_by") or [])
    if component not in hb:
        hb.append(component)
    boots = _boots(st)
    boots.pop(component, None)
    st.update(healthy_by=hb, boots=boots)
    need = ["gui"] + (["agent"] if load_config()["agent"].get("enabled") else [])
    if all(c in hb for c in need):       # every part that runs has worked: probation is over
        st.pop("pending", None)
        st["boots"], st["healthy_by"] = {}, []
        st["healthy"] = {"version": VERSION, "at": time.time(), "by": "+".join(hb)}
    save_update_state(st)
    app_log("update", f"{VERSION} confirmed healthy by {component}")


def on_probation(component: str = None) -> bool:
    """Is this version still being checked? With a component: has that part not proven itself yet?"""
    st = update_state()
    if st.get("pending") != VERSION:
        return False
    return component is None or component not in (st.get("healthy_by") or [])


# ==========================================================================
# Testing Rescue (1.4.2, the owner's call): on the Testing channel, an app-menu entry next to Ally Hub that can roll
# back the test build, go back to Stable or uninstall, even when the test build won't open. It is a standalone bash
# script outside the app folder (updates and rollbacks never touch it) and imports nothing from Ally Hub.
# ==========================================================================

RESCUE_DIR = HOME / ".local/share/allyhub-rescue"
RESCUE_SH = RESCUE_DIR / "rescue.sh"
RESCUE_ICON = RESCUE_DIR / "rescue.svg"
RESCUE_DESKTOP = HOME / ".local/share/applications/allyhub-testing-rescue.desktop"
RESCUE_ON_DESKTOP = HOME / "Desktop/allyhub-testing-rescue.desktop"

RESCUE_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#f59e0b"/>
<circle cx="32" cy="32" r="17" fill="none" stroke="#ffffff" stroke-width="9"/>
<g stroke="#b45309" stroke-width="9"><path d="M20 20l6 6M44 20l-6 6M20 44l6-6M44 44l-6-6"/></g>
<rect x="38" y="40" width="22" height="18" rx="5" fill="#1f2937"/>
<text x="49" y="54" font-family="sans-serif" font-size="13" font-weight="700" fill="#fbbf24" text-anchor="middle">T</text>
</svg>
"""

RESCUE_SCRIPT = r'''#!/usr/bin/env bash
# Ally Hub Testing Rescue. Made by Ally Hub while it's on the Testing channel, so a test build that won't open
# can be rolled back, swapped for Stable or removed. It doesn't use any of Ally Hub's own code on purpose.
APP="$HOME/.local/share/allyhub"
PREV="$APP/previous"
STATE="$APP/update_state.json"
CFG="$HOME/.config/allyhub/config.json"
REPO_URL="https://github.com/@REPO@"
TITLE="Ally Hub Testing Rescue"
NL=$'\n'
ME_MENU="@DESKTOP@"
ME_DESK="@ONDESK@"

pub() { local v="$1"; [ -n "$v" ] || { echo "?"; return; }; echo "$(( ${v%%.*} - 5 )).${v#*.}"; }   # build 6.4.1 = 1.4.1
say() {
    if command -v kdialog >/dev/null 2>&1; then kdialog --title "$TITLE" --msgbox "$1"
    elif command -v zenity >/dev/null 2>&1; then zenity --info --title "$TITLE" --text "$1"
    else printf '%s\n' "$1"; read -r -p "Press Enter to close" _; fi
}
sure() {
    if command -v kdialog >/dev/null 2>&1; then kdialog --title "$TITLE" --warningyesno "$1"
    elif command -v zenity >/dev/null 2>&1; then zenity --question --title "$TITLE" --text "$1"
    else printf '%s [y/N] ' "$1"; read -r a; [ "$a" = y ] || [ "$a" = Y ]; fi
}
pick() {
    local text="Ally Hub $(pub "$(cat "$APP/VERSION" 2>/dev/null)") is a test build. What would you like to do?"
    if command -v kdialog >/dev/null 2>&1; then
        kdialog --title "$TITLE" --menu "$text" rollback "Roll back to the version before this one" \
            stable "Go back to Stable (keeps your settings)" uninstall "Uninstall Ally Hub"
    elif command -v zenity >/dev/null 2>&1; then
        zenity --list --title "$TITLE" --text "$text" --column key --column Action --hide-column 1 \
            rollback "Roll back to the version before this one" stable "Go back to Stable (keeps your settings)" \
            uninstall "Uninstall Ally Hub"
    else
        echo "$text" >&2; echo "1) Roll back  2) Go back to Stable  3) Uninstall" >&2; read -r n
        case "$n" in 1) echo rollback;; 2) echo stable;; 3) echo uninstall;; esac
    fi
}
in_terminal() {     # long jobs run where you can watch them
    if command -v konsole >/dev/null 2>&1; then konsole -e bash -c "$1; echo; read -r -p 'Press Enter to close this window' _"
    else bash -c "$1"; fi
}
remove_me() { rm -f "$ME_MENU" "$ME_DESK"; rm -rf "$HOME/.local/share/allyhub-rescue"; }

case "$(pick)" in
rollback)
    if [ ! -f "$PREV/core.py" ]; then
        say "There's no earlier version saved on this handheld. Use \"Go back to Stable\" instead."; exit 0
    fi
    bad="$(cat "$APP/VERSION" 2>/dev/null)"; good="$(cat "$PREV/VERSION" 2>/dev/null)"
    sure "Roll back from $(pub "$bad") to $(pub "$good")?${NL}${NL}Ally Hub won't install $(pub "$bad") again." || exit 0
    systemctl --user stop allyhub-agent.service 2>/dev/null
    pkill -f "$APP/allyhub.py" 2>/dev/null
    cp -rf "$PREV/." "$APP/" && rm -rf "$APP/__pycache__"
    python3 - "$STATE" "$bad" "$good" <<'PY'
import json, sys, time
path, bad, good = sys.argv[1:4]
try:
    st = json.load(open(path))
except Exception:
    st = {}
st.setdefault("bad", [])
if bad and bad not in st["bad"]:
    st["bad"].append(bad)
st.pop("pending", None)
st["rolled_back"] = {"from": bad, "to": good, "reason": "Testing Rescue", "at": time.time()}
json.dump(st, open(path, "w"), indent=2)
PY
    systemctl --user is-enabled -q allyhub-agent.service 2>/dev/null && systemctl --user start allyhub-agent.service
    say "Rolled back to $(pub "$good"). Open Ally Hub as usual.${NL}${NL}You're still on the Testing channel; the next test build will be offered when it's out."
    ;;
stable)
    sure "Go back to Stable?${NL}${NL}Ally Hub downloads the stable version and reinstalls it. Your settings stay." || exit 0
    python3 - "$CFG" <<'PY'
import json, sys
path = sys.argv[1]
try:
    cfg = json.load(open(path))
except Exception:
    cfg = {}
cfg.setdefault("updates", {})["channel"] = "stable"
json.dump(cfg, open(path, "w"), indent=2)
PY
    pkill -f "$APP/allyhub.py" 2>/dev/null
    tmp="$(mktemp -d)"
    in_terminal "git clone -q --depth 1 '$REPO_URL' '$tmp/AllyHub' && bash '$tmp/AllyHub/scripts/install.sh' && rm -f '$ME_MENU' '$ME_DESK' && rm -rf '$HOME/.local/share/allyhub-rescue'; rm -rf '$tmp'"
    ;;
uninstall)
    sure "Uninstall Ally Hub?${NL}${NL}Your mods, apps and backups stay." || exit 0
    pkill -f "$APP/allyhub.py" 2>/dev/null
    if [ -f "$APP/uninstall.sh" ]; then
        in_terminal "bash '$APP/uninstall.sh'"
    else
        tmp="$(mktemp -d)"
        in_terminal "git clone -q --depth 1 '$REPO_URL' '$tmp/AllyHub' && bash '$tmp/AllyHub/scripts/uninstall.sh'; rm -rf '$tmp'"
    fi
    remove_me
    ;;
esac
'''


def testing_rescue_files() -> dict:
    """{path: (text, mode)} for the Testing Rescue (script, icon, app-menu entry, desktop icon when Ally Hub has one)."""
    script = (RESCUE_SCRIPT.replace("@REPO@", repo_name()).replace("@DESKTOP@", str(RESCUE_DESKTOP))
              .replace("@ONDESK@", str(RESCUE_ON_DESKTOP)))
    entry = ("[Desktop Entry]\nType=Application\nName=Ally Hub Testing Rescue\n"
             "Comment=Roll back the Ally Hub test build, go back to Stable, or uninstall\n"
             f"Exec=bash {RESCUE_SH}\nIcon={RESCUE_ICON}\nTerminal=false\nCategories=Utility;\n")
    files = {RESCUE_SH: (script, 0o755), RESCUE_ICON: (RESCUE_SVG, 0o644), RESCUE_DESKTOP: (entry, 0o755)}
    if (HOME / "Desktop/allyhub.desktop").exists():
        files[RESCUE_ON_DESKTOP] = (entry, 0o755)
    return files


def sync_testing_rescue(cfg: dict = None) -> bool:
    """Testing channel: make sure the rescue entry exists (and is current). Stable: remove it. True if it's there."""
    on = update_channel(cfg) == "testing"
    if not on:
        for p in (RESCUE_DESKTOP, RESCUE_ON_DESKTOP):
            p.unlink(missing_ok=True)
        shutil.rmtree(RESCUE_DIR, ignore_errors=True)
        return False
    for path, (text, mode) in testing_rescue_files().items():
        try:
            if read_text(path) != text:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            path.chmod(mode)
        except OSError:
            pass
    return RESCUE_SH.exists()


def changelog_text() -> str:
    """Every release's notes, newest first, for the Updates page."""
    text = read_text(APP_DIR / "CHANGELOG.md") or read_text(APP_DIR.parent / "docs" / "CHANGELOG.md")
    text = re.sub(r"^# Changelog\s*", "", text)
    return text.strip()


def changelog_section(version: str = None) -> str:
    text = read_text(APP_DIR / "CHANGELOG.md") or read_text(APP_DIR.parent / "docs" / "CHANGELOG.md")
    for v in dict.fromkeys((display_version(version), version or VERSION)):   # public number first, then the build
        m = re.search(rf"^## {re.escape(v)}\b.*?(?=^## |\Z)", text, re.M | re.S)
        if m:
            return m.group(0).strip()
    return ""
