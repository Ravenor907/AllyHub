#!/usr/bin/env python3
"""
Ally Hub test suite. Runs without Qt or a real handheld:

  python3 tests/run_tests.py

- compile: every module and shell script parses
- core:    scrubbing, versions, reports, profiles, LED writes, catalog commands
- agent:   game detection, lighting decisions, health log, phone remote (real HTTP)
- update:  install from a fake GitHub tarball, crash-loop rollback, bad-version skip
- gui:     builds every page and drives every action through a stand-in Qt (tests/mockqt)

Each section runs in a subprocess with a throwaway HOME. Exit code 0 means all passed.
"""

import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"            # the code lives in app/; install.sh and uninstall.sh in scripts/
MOCKQT = ROOT / "tests" / "mockqt"


def run_section(name: str, code: str, mock_qt: bool = False, timeout: int = 120) -> bool:
    with tempfile.TemporaryDirectory() as home:
        env = dict(os.environ, HOME=home, USER="deck", PYTHONDONTWRITEBYTECODE="1")
        paths = [str(APP)] + ([str(MOCKQT)] if mock_qt else [])
        env["PYTHONPATH"] = os.pathsep.join(paths)
        env.pop("XDG_CURRENT_DESKTOP", None)
        prelude = textwrap.dedent(f"""
            import sys, os, json, time
            HOME = {home!r}
            def check(cond, msg):
                if not cond:
                    raise AssertionError(msg)
                print("  ok:", msg)
        """)
        try:
            p = subprocess.run([sys.executable, "-c", prelude + textwrap.dedent(code)],
                               env=env, cwd=home, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            print(f"FAIL {name}: timed out")
            return False
        ok = p.returncode == 0
        print(f"{'PASS' if ok else 'FAIL'} {name}")
        out = (p.stdout + p.stderr).strip()
        if out and (not ok or "-v" in sys.argv):
            print(textwrap.indent(out[-4000:], "    "))
        return ok


COMPILE = """
import py_compile, subprocess
for f in ("allyhub.py", "core.py", "agent.py", "gui.py"):
    py_compile.compile(os.path.join({root!r}, "app", f), doraise=True, cfile=os.path.join(HOME, f + "c"))
    check(True, f"compiles: " + f)
_un = open(os.path.join({root!r}, "scripts", "uninstall.sh")).read()
check("homebrew/plugins/AllyHub" in _un and "cef_remove_shortcuts" in _un, "the uninstaller also removes the Quick Access panel and the library tile")
for sh in ("install.sh", "uninstall.sh"):
    check(subprocess.run(["bash", "-n", os.path.join({root!r}, "scripts", sh)]).returncode == 0, "bash -n " + sh)
v = open(os.path.join({root!r}, "VERSION")).read().strip()
import re
check(re.fullmatch(r"\\d+\\.\\d+\\.\\d+", v), "VERSION is x.y.z: " + v)
cl = open(os.path.join({root!r}, "docs", "CHANGELOG.md")).read()
maj, mi, pa = (int(x) for x in v.split("."))
pub = f"{{maj - 5}}.{{mi}}.{{pa}}" if maj > 5 else v      # public number (see core.display_version)
check(f"## {{pub}}" in cl, "CHANGELOG has a section for " + pub)
# the repo top level stays tidy: everything else lives in folders
top = sorted(x for x in os.listdir({root!r}) if x not in (".git", "__pycache__"))
check(top == [".claude", ".github", ".gitignore", "LICENSE", "README.md", "VERSION", "app", "assets", "docs",
              "scripts", "tests"], "tidy repo top level: " + ", ".join(top))
# install.sh run from scripts/ finds and copies every app file (only its copy step, no network)
inst = open(os.path.join({root!r}, "scripts", "install.sh")).read()
check("Categories=Utility;\\n" in inst and "Settings;Game" not in inst, "the installer puts Ally Hub in one menu folder")
check("--first-install" in inst and 'FRESH' in inst, "a fresh install sets itself up (helper on, Game Mode entry, setup)")
copy_part = inst.split('rm -rf "$APP_DIR/__pycache__"')[0]
tmp_sh = os.path.join({root!r}, "scripts", ".copy_test.sh")
open(tmp_sh, "w").write(copy_part)
try:
    subprocess.run(["bash", tmp_sh], env=dict(os.environ, HOME=HOME), check=True, capture_output=True)
finally:
    os.remove(tmp_sh)
inst_dir = os.path.join(HOME, ".local/share/allyhub")
want = ["allyhub.py", "core.py", "agent.py", "gui.py", "allyhub.svg", "VERSION", "CHANGELOG.md", "README.md",
        "install.sh", "uninstall.sh"]
check(sorted(os.listdir(inst_dir)) == sorted(want), "install.sh copies every file flat from the folders")
rd = open(os.path.join({root!r}, "README.md")).read()
check("scripts/install.sh" in rd, "README install command points at scripts/install.sh")
check(f"badge/version-{{pub}}-" in rd, "README badge shows " + pub)
""".format(root=str(ROOT))

CORE = r"""
import core
core.update_config(lambda c: c["agent"].__setitem__("remote_pin", "482913"))
s = core.scrub(f"{HOME}/x 192.168.1.20 aa:bb:cc:dd:ee:ff deck pin=1234 github_pat_ABCDEFGHIJKLMNOPQRSTUV me@x.com 482913")
check("192.168" not in s and "<ip>" in s, "scrubs IPs")
check("aa:bb" not in s, "scrubs MACs")
check(HOME not in s and "~/x" in s, "scrubs home path")
check("deck" not in s, "scrubs username")
check("github_pat_" not in s, "scrubs tokens")
check("me@x.com" not in s, "scrubs emails")
check("482913" not in s, "scrubs remote PIN")
import shutil, subprocess
from pathlib import Path
if shutil.which("curl") and shutil.which("bash"):
    _scr = Path(HOME) / "inst.sh"
    _scr.write_text('[ "$X" = 1 ] || X=1 exec env X=1 "$0" "$@"\necho "ran as $0"\n')
    _r = subprocess.run(["bash", "-c", core.fetch_run(_scr.as_uri())], capture_output=True, text=True)
    check(_r.returncode == 0 and "ran as bash" in _r.stdout, "fetched installers still re-run themselves like curl | sh: " + _r.stdout + _r.stderr)
    _r = subprocess.run(["bash", "-c", core.fetch_run((Path(HOME) / "missing.sh").as_uri())], capture_output=True, text=True)
    check(_r.returncode != 0, "a failed download is never run")
_zip = Path(HOME) / "plug.zip"
import zipfile as _zf, hashlib as _hl
with _zf.ZipFile(_zip, "w") as z:
    z.writestr("Plug/plugin.json", "{}")
_good = _hl.sha256(_zip.read_bytes()).hexdigest()
check(core.store_artifact_hash({"versions": [{"hash": _good}]}) == _good and core.store_artifact_hash({"versions": [{"hash": "x"}]}) == "",
      "store hash read")
_c = core.decky_store_install_cmd(_zip.as_uri(), "0" * 64).split("python3 -m zipfile")[0] + "echo EXTRACTED"
_r = subprocess.run(["bash", "-c", _c], capture_output=True, text=True)
check(_r.returncode != 0 and "EXTRACTED" not in _r.stdout, "a plugin download that doesn't match the store's checksum is never installed")
_c = core.decky_store_install_cmd(_zip.as_uri(), _good).split("python3 -m zipfile")[0] + "echo EXTRACTED"
check("EXTRACTED" in subprocess.run(["bash", "-c", _c], capture_output=True, text=True).stdout, "a matching one goes ahead")
import urllib.request as _ur, urllib.error as _ue, io as _io
_seen_auth = []
class _Resp(_io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): pass
def _fake_open(req, timeout=0):
    _seen_auth.append(bool(req.get_header("Authorization")))
    if req.get_header("Authorization"):
        raise _ue.HTTPError(req.full_url, 401, "Bad credentials", {}, _io.BytesIO(b"{}"))
    return _Resp(b"6.9.9")
_uo = _ur.urlopen
core.save_github_token("github_pat_EXPIREDEXPIREDEXPIRED123")
check(oct(os.stat(core.TOKEN_FILE).st_mode & 0o777) == "0o600", "the access key file is private")
_ur.urlopen = _fake_open
check(core.remote_version("main") == "6.9.9" and _seen_auth == [True, False], "an expired access key doesn't stop updates")
_ur.urlopen = _uo
core.TOKEN_FILE.unlink()
core.DATA_DIR.chmod(0o755); core.secure_data_dir()
check(oct(core.DATA_DIR.stat().st_mode & 0o777) == "0o700", "Ally Hub's data folder is private")
_me = core.MENU_ENTRIES[0]; _me.parent.mkdir(parents=True, exist_ok=True)
_me.write_text("[Desktop Entry]\nName=Ally Hub\nCategories=Utility;Settings;Game;\n")
check(core.tidy_menu_entry() and "Categories=Utility;\n" in _me.read_text() and not core.tidy_menu_entry(),
      "Ally Hub shows once in the app menu (Utilities), not under Games, Utilities and System")
_me.unlink()
import socket as _sock
_h = _sock.gethostname()
_s2 = core.scrub(f"steam 76561198012345678 on {_h} ok")
check("76561198012345678" not in _s2 and (len(_h) < 3 or _h.lower() in ("localhost", "steamdeck") or _h not in _s2),
      "scrubs Steam ids and the device name: " + _s2)
check(core.parse_version("3.10.0") > core.parse_version("3.9.9"), "version compare")
check(core.queue_report("crash", "t", "d") is None, "no reports while reporting is off")
check(core.LAST_QUEUE == "off" and "Turn on" in core.report_hint(), "explains reporting is off")
core.update_config(lambda c: c["updates"].__setitem__("reporting", True))
p = core.queue_report("crash", "boom", "Traceback in /home/deck/x 10.0.0.1")
check(core.LAST_QUEUE == "no_key" and "access key" in core.report_hint(), "flags a missing access key")
check(p is not None and p.exists(), "queues a report")
rep = json.load(open(p))
check("10.0.0.1" not in rep["body"], "report body scrubbed")
check(core.queue_report("crash", "boom", "again") is None, "dedupes same fingerprint")
check(core.LAST_QUEUE == "duplicate" and "already reported" in core.report_hint(), "explains duplicates instead of saying reporting is off")
try:
    1 / 0
except ZeroDivisionError:
    check(core.report_exception("test") is not None, "report_exception captures tracebacks")
check(core.upload_reports() == (0, 0), "no upload without a token")
cfg = core.load_config()
check(cfg["theme"]["preset"] in core.THEMES, "default theme exists")
for name in core.THEMES:
    pal = core.theme_palette({"preset": name})
    check(all(k in pal for k in ("bg", "accent", "accent2", "on_accent", "hero")), "theme complete: " + name)
check(core.battery_color(0) == (255, 0, 0) and core.battery_color(100) == (0, 255, 0), "battery colors")
check(core.normalize_mac("AA-BB-CC-DD-EE-FF") == "aabbccddeeff" and core.normalize_mac("x") is None, "MAC parsing")
import subprocess
bad = [i.id for i in core.CATALOG if subprocess.run(["bash", "-n", "-c", i.install]).returncode]
check(not bad, "all install commands parse")
check(len({i.id for i in core.CATALOG}) == len(core.CATALOG), "catalog ids unique")
cats = set(core.MOD_CATEGORIES + core.APP_CATEGORIES)
check(all(i.category in cats for i in core.CATALOG), "every item has a page")
prof = core.build_profile({"flatpaks": {"a.b.C"}, "decky": {}})
plan = core.profile_plan(prof, {"flatpaks": set(), "decky": {}})
check(plan["flatpaks"] == ["a.b.C"], "profile round-trip")
# lighting effects
import random
for kind in core.EFFECT_TYPES:
    e = core.normalize_effect({"type": kind, "colors": ["#ff0000", "#00ff00", "#0000ff", "#ffffff", "#123456"]})
    lo, hi = core.EFFECT_TYPES[kind]["colors"]
    check(lo <= len(e["colors"]) <= hi, f"{kind}: color count clamped")
    frames = {core.effect_frame(e, random.uniform(0, 600)) for _ in range(300)}
    check(all(0 <= c <= 255 for f in frames for c in f), f"{kind}: frames in range")
    if kind != "static":
        check(len(frames) >= 2, f"{kind}: actually animates")
for name, p in core.PRESETS.items():
    check(core.effect_label(p) == name, f"preset {name} renders and is recognized")
bad = core.normalize_effect({"type": "nope", "colors": ["red", 5], "speed": "x", "param": 9})
check(bad["type"] == "static" and bad["colors"] and bad["speed"] == 1.0 and bad["param"] == 1.0, "garbage effects are made safe")
check(core.lookup_effect("#00ff00")["colors"] == ["#00ff00"], "hex lookup")
check(core.lookup_effect("preset:Aurora")["type"] == "wave", "preset lookup")
check(core.lookup_effect("preset:Missing") is None, "unknown preset")
check(core.base_effect({"rgb": {"rgb": [1, 2, 3]}, "lighting": {}})["colors"] == ["#010203"], "a plain saved color still works")
# screen scaling
from pathlib import Path
drm = Path(HOME) / "drm"
for name, mode, want in (("card1-eDP-1", "1920x1080", 1.5), ("card1-eDP-1", "1280x800", 1.0),
                         ("card1-eDP-1", "1200x1920", 1.75), ("card1-eDP-1", "2560x1600", 2.0)):
    import shutil; shutil.rmtree(drm, ignore_errors=True)
    (drm / name).mkdir(parents=True); (drm / name / "modes").write_text(mode + "\n1280x720\n")
    core.DRM_ROOT = drm
    check(core.auto_ui_scale() == want, f"auto scale {mode} -> {want}")
shutil.rmtree(drm)
check(core.auto_ui_scale() == 1.0, "no panel info -> 100%")
check(core.ui_scale({"ui_scale": 1.25}) == 1.25 and core.ui_scale({"ui_scale": "junk"}) == 1.0, "manual scale")
# LEDs
led = Path(HOME) / "leds" / "ally:rgb:joystick_rings"
led.mkdir(parents=True)
(led / "multi_index").write_text("red green blue"); (led / "multi_intensity").write_text("0 0 0")
(led / "max_brightness").write_text("255"); (led / "brightness").write_text("0")
(led / "effect_index").write_text("monocolor breathe"); (led / "effect").write_text("0")
core.LED_ROOT = Path(HOME) / "leds"
leds = core.find_leds()
check(len(leds) == 1 and "effect" in leds[0].enums, "finds LED + effects")
check(core.apply_lighting((1, 2, 3), 99, {"effect": "breathe"}), "writes lighting")
# ROG Xbox Ally X kernel: four zones, each one packed 0xRRGGBB value
z = Path(HOME) / "leds2" / "ally:rgb:joystick_rings"; z.mkdir(parents=True)
(z / "multi_index").write_text("rgb rgb rgb rgb"); (z / "multi_intensity").write_text("0 0 0 0")
(z / "multi_max_intensity").write_text("16777215 16777215 16777215 16777215")
(z / "max_brightness").write_text("255"); (z / "brightness").write_text("255")
core.LED_ROOT = Path(HOME) / "leds2"
zl = core.find_leds()
check(zl and zl[0].channels == ["rgb"] * 4 and zl[0].channel_max == [16777215] * 4, "reads packed 4-zone LED")
check(core.apply_lighting((255, 128, 0), 255, {}), "writes packed LED")
check((z / "multi_intensity").read_text() == " ".join([str(0xFF8000)] * 4), "packs color as 0xRRGGBB per zone")
check(core.channel_value("red", (200, 0, 0), 1000) == 784, "scales separate channels to their max")
check(core.channel_value("rgb", (255, 0, 0), 255, "clamped") == 255, "clamped encoding reproduces the blue-only bug")
check(core.channel_value("rgb", (255, 0, 0), 255) == 0xFF0000, "default packed encoding ignores a 255 cap")
check(core.channel_value("rgb", (255, 0, 0), 0, "packed_bgr") == 0x0000FF, "BGR encoding")
t = core.write_test_color(zl, (0, 255, 0), "packed")
check(t["ok"] and t["readback"] == [" ".join([str(0x00FF00)] * 4)], "test write records the readback")
pk = core.hid_packets("solid", (255, 0, 0))
check(all(len(p) == 64 for p in pk) and pk[3][:7] == bytes([0x5A, 0xB3, 0, 0, 255, 0, 0]), "HID solid red packet")
check(pk[1][:5] == bytes([0x5A, 0xD1, 0x09, 0x01, 0x02]), "RGB enable sent before colors (HueSync)")
check(pk[-2][:2] == bytes([0x5A, 0xB5]) and pk[-1][:2] == bytes([0x5A, 0xB4]), "HID set + apply packets")
check(core.hid_effect_packets(core.PRESETS["Rainbow"], 255)[3][3] == 0x02, "color cycle maps to rainbow mode")
check(core.led_intensities(zl[0], (255, 0, 0), "hex") == " ".join(["0xff0000"] * 4), "hex encoding like HueSync")
t = core.write_test_color(zl, (255, 0, 0), "hex")
check(t["matches"] is True, "hex readback parsed as the same number")
_rt = core.read_text
core.read_text = lambda p, *a: "255 255 255 255" if Path(p).name == "multi_intensity" else _rt(p, *a)
check(core.write_test_color(zl, (255, 255, 255), "hex")["matches"] is False, "detects a kernel that changed the value")
core.read_text = _rt
# HID report descriptors: vendor 0xFF31/0x80 lighting, LampArray 0x59/0x01, plain gamepad
LIGHT_DESC = bytes([0x06, 0x31, 0xFF, 0x09, 0x80, 0xA1, 0x01, 0x85, 0x5A, 0x09, 0x01, 0xC0])
LAMP_DESC = bytes([0x05, 0x59, 0x09, 0x01, 0xA1, 0x01, 0x09, 0x02, 0xA1, 0x02, 0xC0, 0xC0])
PAD_DESC = bytes([0x05, 0x01, 0x09, 0x05, 0xA1, 0x01, 0xC0])
check(core.hid_collections(LIGHT_DESC) == [(0xFF31, 0x80)], "parses vendor usage page")
check(core.hid_collections(LAMP_DESC) == [(0x59, 0x01)], "parses LampArray, ignores nested collections")
hr = Path(HOME) / "hidraw"
for n, desc, ids in (("hidraw3", PAD_DESC, "00000B05:00001B4C"), ("hidraw5", LIGHT_DESC, "00000B05:00001B4C"),
                     ("hidraw6", LAMP_DESC, "00000B05:00001B4C"), ("hidraw9", LIGHT_DESC, "0000046D:0000C52B")):
    (hr / n / "device").mkdir(parents=True)
    (hr / n / "device" / "uevent").write_text(f"DRIVER=hid-generic\nHID_ID=0003:{ids}\n")
    (hr / n / "device" / "report_descriptor").write_bytes(desc)
core.HIDRAW_ROOT = hr
core.DEV_ROOT = Path(HOME) / "dev"
nodes = core.ally_hid_nodes([])
check(nodes["lighting"] == core.DEV_ROOT / "hidraw5", "picks the 0xFF31/0x80 lighting interface, not the gamepad")
check(nodes["dynamic"] == core.DEV_ROOT / "hidraw6", "finds the Dynamic Lighting interface")
check(("0b05", "1b4c") in nodes["ids"] and ("046d", "c52b") not in nodes["ids"], "only the ASUS controller")
cmd = core.led_permission_cmd([])
check(cmd.count("sudo ") == 1 and "MODE:=" in cmd and "1b4c" in cmd and core.UDEV_LED_RULE in cmd
      and core.HID_PERMISSION_RULE in cmd and core.RULES_MARKER in cmd,
      "one password prompt covers the ring files and the lighting chip")
check("hid hidraw5 0b05:1b4c usages ff31/0080" in core.lighting_diagnostics(), "diagnostics list HID usages")
core.HIDRAW_ROOT = Path(HOME) / "nohidraw"
check(core.hid_brightness_level(0) == 0 and core.hid_brightness_level(255) == 3, "HID brightness levels")
d = core.lighting_diagnostics()
check("multi_max_intensity" in d and "16777215" in d, "diagnostics include attribute values")
core.LED_ROOT = Path(HOME) / "leds"
check((led / "multi_intensity").read_text() == "1 2 3" and (led / "effect").read_text() == "breathe", "LED values")
# software effects must switch a hardware rainbow/breathe mode back to plain color, or nothing shows
leds = core.find_leds()
check(core.static_mode(leds[0]) == {"effect": "monocolor"}, "finds plain-color hardware mode")
check(core.apply_lighting((9, 8, 7), 200, None, leds) and (led / "effect").read_text() == "monocolor",
      "plain-color mode forced for software effects")
(led / "effect").write_text("breathe")
check(core.apply_lighting((9, 8, 6), 200, None, leds) and (led / "multi_intensity").read_text() == "9 8 6"
      and (led / "effect").read_text() == "breathe",
      "mode not rewritten every frame")
leds = core.find_leds()
(led / "effect").chmod(0o444)
check(core.apply_lighting((5, 5, 5), 200, None, leds) and (led / "multi_intensity").read_text() == "5 5 5",
      "read-only mode attribute doesn't block the color")
(led / "effect").chmod(0o644)
check("ally:rgb:joystick_rings" in core.lighting_diagnostics(), "lighting diagnostics list LEDs")
# Spiral: per-zone colors, options, chip mode, and zone streaming
sp = core.normalize_effect({"type": "spiral", "layout": "bogus", "direction": "ccw"})
check(sp["layout"] == "linked" and sp["direction"] == "ccw" and sp["rainbow"] is True, "spiral options normalized")
check("layout" not in core.normalize_effect({"type": "wave"}), "other effects don't grow spiral keys")
own = core.normalize_effect({"type": "spiral", "rainbow": False, "colors": []})
check(own["rainbow"] is False and len(own["colors"]) == 2, "unticking rainbow gives two colors to edit")
z = core.zone_frames(core.PRESETS["RGB Spiral"], 0.3)
check(len(z) == 4 and len(set(z)) == 4, "linked spiral: four different zone colors")
same = core.zone_frames(dict(core.PRESETS["RGB Spiral"], layout="same"), 0.3)
check(same[0] == same[2] and same[1] == same[3] and same[0] != same[1], "matching sticks show the same pattern")
mir = core.zone_frames(dict(core.PRESETS["RGB Spiral"], layout="mirror"), 0.7)
check(mir[0] != mir[2], "mirrored sticks spin opposite ways")
check(core.zone_frames(core.PRESETS["RGB Spiral"], 0.0) != core.zone_frames(core.PRESETS["RGB Spiral"], 0.5),
      "spiral moves over time")
check(len(set(core.zone_frames(core.PRESETS["Aurora"], 1.0))) == 1, "other effects light all zones alike")
chip = core.hid_effect_packets(dict(core.PRESETS["RGB Spiral"], engine="chip", direction="ccw"), 255)
b3 = [p for p in chip if p[1] == 0xB3]
check(b3 and b3[0][3] == 0x03 and b3[0][8] == 0x01, "chip spiral: built-in mode 3 with direction")
check(core.uses_chip_effect(dict(core.PRESETS["RGB Spiral"], engine="chip")) and core.hid_streams("m6")
      and not core.hid_streams("m3"), "streaming only for commit-once methods")
frames = []
_hs = core.hid_send
core.hid_send = lambda node, packets, feature=False, gap=0: (frames.append(list(packets)), (True, ""))[1]
_nodes = core._stream_nodes
core._stream_nodes = lambda leds: {"lighting": Path("/dev/hidraw5"), "dynamic": None, "ids": set()}
_off = core.kernel_lights_off
core.kernel_lights_off = lambda leds: "off"
core.hid_reset_session()
check(core.hid_zone_frame([(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)], 128, [], "m6"), "zone frame sent")
check(core.hid_zone_frame([(0, 0, 255)] * 4, 255, [], "m6"), "second frame sent")
f1, f2 = frames
check(any(p[1] == 0xB5 for p in f1) and [p[1] for p in f2] == [0xD1] + [0xB3] * 4,
      "first frame commits, later frames are bare zone commands (no chip-memory writes)")
check([tuple(p[4:7]) for p in f1 if p[1] == 0xB3] == [(128, 0, 0), (0, 128, 0), (0, 0, 128), (128, 128, 128)],
      "brightness folded into the colors, each zone its own color")
core.hid_send, core._stream_nodes, core.kernel_lights_off = _hs, _nodes, _off
core.hid_reset_session()
# public version numbers: build 6.x.y is shown as 1.x.y
check(core.display_version("6.0.0") == "1.0.0" and core.display_version("6.1.3") == "1.1.3"
      and core.display_version("7.0.0") == "2.0.0" and core.display_version("5.0.0") == "5.0.0",
      "build numbers map to public versions")
check(core.parse_version("6.0.0") > core.parse_version("5.0.0"), "installed lower builds see 1.0.0 (build 6.0.0) as newer")
check(core.changelog_section("6.0.0").startswith("## 1.0.0"), "release notes found by public version")
check("Ally Hub: " + core.display_version() + " (build " + core.VERSION + ")" in core.environment_summary(),
      "reports show the public version and the build")
check(core.display_version().count(".") == 2 and not core.display_version().startswith("6."),
      "this release shows a public version, not the build number")
try:
    raise KeyboardInterrupt()
except KeyboardInterrupt:
    check(core.report_exception("gui") is None, "closing the app (Ctrl+C) isn't reported as a crash")
check(core.pause_agent() is False, "pausing a stopped agent is a no-op")
check(core.hid_method("nope") == core.HID_METHODS[core.DEFAULT_HID_METHOD], "unknown method falls back safely")
# ---- Performance: Game Boost + Tune-up on a fake kernel ----
fk = Path(HOME) / "fakekernel"
for i in range(2):
    pol = fk / "cpufreq" / f"policy{i}"; pol.mkdir(parents=True)
    (pol / "energy_performance_preference").write_text("balance_power")
    (pol / "energy_performance_available_preferences").write_text(
        "default performance balance_performance balance_power power")
core.CPUFREQ_ROOT = fk / "cpufreq"
core.ppd_available = lambda: False
core._BACKEND_CACHE["at"] = 0.0
check(core.boost_backend() == "epp" and core.boost_ready(), "Game Boost finds the CPU energy preference")
check(core.boost_target("epp", False) == "performance" and core.boost_target("epp", True) == "balance_performance",
      "plugged in boosts fully, battery boosts a bit less")
check(core.boost_target("ppd", True) is None, "power-profiles-daemon is left alone on battery")
rec = core.boost_apply(False)
check(rec and rec["before"] == "balance_power" and core.epp_current() == "performance", "boost switches every core")
check(all(f.read_text() == "performance" for f in core.epp_files()), "all policies changed")
check(core.boost_apply(False) is None, "boosting twice changes nothing")
check(core.boost_restore(rec) and core.epp_current() == "balance_power", "restores the original setting")
rec = core.boost_apply(False)
for f in core.epp_files():
    f.write_text("power")
check(not core.boost_restore(rec) and core.epp_current() == "power",
      "doesn't fight a change SteamOS or the user made mid-game")
pc = core.boost_permission_cmd()
check(pc and "tmpfiles.d" in pc and "energy_performance_preference" in pc and pc.startswith("sudo sh -c "),
      "one password prompt makes the boost permission stick")
sysd = fk / "sys"
for k, v in {"vm/swappiness": "60", "vm/page-cluster": "3", "vm/vfs_cache_pressure": "100",
             "vm/dirty_bytes": "0", "vm/dirty_background_bytes": "0", "vm/compaction_proactiveness": "20",
             "vm/dirty_ratio": "20", "vm/dirty_background_ratio": "10"}.items():
    (sysd / k).parent.mkdir(parents=True, exist_ok=True); (sysd / k).write_text(v)
thp = fk / "thp"; thp.mkdir()
(thp / "enabled").write_text("always [madvise] never")
(thp / "defrag").write_text("always defer defer+madvise [madvise] never")
core.SYSCTL_ROOT, core.THP_ROOT = sysd, thp
core.MODULES_ROOT = fk / "modules"
(fk / "modules" / os.uname().release).mkdir(parents=True)
(fk / "modules" / os.uname().release / "modules.dep").write_text(
    "kernel/drivers/block/zram/zram.ko.zst: kernel/lib/zstd.ko.zst\nkernel/drivers/misc/ntsync.ko.zst:\n")
core.PROC_SWAPS = fk / "swaps"; core.PROC_SWAPS.write_text("Filename Type Size Used Priority\n/home/swapfile file 1 0 -2\n")
core.MEMINFO = fk / "meminfo"; core.MEMINFO.write_text("MemTotal:       24000000 kB\n")
core.NTSYNC_DEV = fk / "ntsync"
check(core.thp_get("enabled") == "madvise" and "defer+madvise" in core.thp_choices("defrag"), "reads huge page options")
plan = core.tuneup_plan()
check(plan == {"zram": True, "memory": True, "hugepages": True, "splitlock": False, "ntsync": True},
      "tune-up plan follows what the kernel has (no split-lock knob here)")
items = {i["key"]: i["state"] for i in core.tuneup_items()}
check(items == {"zram": "off", "memory": "off", "hugepages": "off", "splitlock": "na", "ntsync": "off"},
      "tune-up status before applying")
snap = core.tuneup_snapshot()
check(snap["sysctl"]["vm.swappiness"] == "60" and snap["thp"]["enabled"] == "madvise", "snapshot keeps the originals")
cmd = core.tuneup_apply_cmd()
check(cmd.startswith("sudo sh -c ") and cmd.count("sudo ") == 1, "tune-up is one password prompt")
for want in ("vm.swappiness = 100", "vm.page-cluster = 0", "vm.vfs_cache_pressure = 50", "zram.sh",
             "allyhub-zram.service", "defer+madvise", "/always", "ntsync", core.TUNEUP_SYSCTL):
    check(want in cmd or want.replace("/", "") in cmd, "tune-up writes " + want)
check("split_lock" not in cmd, "skips settings this kernel doesn't have")
check(str(24000000 * 1024 // 2 // (1 << 20) * (1 << 20)) in cmd, "zram is half the RAM")
check(all(p.startswith(("/etc/", str(fk))) for p in __import__("re").findall(r"tee (\S+)", cmd)),
      "tune-up only writes to /etc (SteamOS's root stays read-only)")
check(subprocess.run(["bash", "-n", "-c", cmd]).returncode == 0, "tune-up command parses")
undo = core.tuneup_undo_cmd(snap)
check("vm.swappiness=60" in undo and "madvise" in undo and "allyhub-zram.service" in undo,
      "undo restores the saved values and removes the zram swap")
check("vm.dirty_bytes=0" not in undo and "vm.dirty_ratio=20" in undo
      and undo.index("vm.dirty_ratio=20") > undo.index("vm.vfs_cache_pressure"),
      "undo puts the dirty ratios back last instead of writing 0 bytes (the kernel refuses that)")
check("sysctl -q --system" in core.tuneup_undo_cmd({}), "undo without a snapshot reloads SteamOS's values")
check("rm -rf" not in undo and "$(touch" not in core.tuneup_undo_cmd({"sysctl": {"vm.x": "$(touch /tmp/p)"}}),
      "undo ignores junk in the saved snapshot")
check(subprocess.run(["bash", "-n", "-c", undo]).returncode == 0, "undo command parses")
(sysd / "vm/vfs_cache_pressure").write_text("50"); (sysd / "vm/dirty_bytes").write_text("268435456")
(sysd / "vm/dirty_background_bytes").write_text("67108864"); (sysd / "vm/compaction_proactiveness").write_text("0")
(thp / "enabled").write_text("[always] madvise never")
core.PROC_SWAPS.write_text("Filename Type Size Used Priority\n/dev/zram0 partition 1 0 100\n")
items = {i["key"]: i["state"] for i in core.tuneup_items()}
check(items["zram"] == items["memory"] == items["hugepages"] == "on" and items["ntsync"] == "off",
      "tune-up status reads the live kernel values")
zs = core.zram_script(1 << 30)
check("swapon -p 100" in zs and "exit 0" in zs and subprocess.run(["sh", "-n", "-c", zs]).returncode == 0,
      "zram script parses and leaves an existing zram alone")
stop = zs[zs.index("stop)"):]
check(f"[ -e {core.ZRAM_MARKER} ] || exit 0" in stop and stop.index(core.ZRAM_MARKER) < stop.index("swapoff")
      and f"&& touch {core.ZRAM_MARKER}" in zs, "only the zram Ally Hub started is ever switched off")
core.ZRAM_GENERATOR_CONFIGS = (str(fk / "zram-generator.conf"),)
(fk / "zram-generator.conf").write_text("[zram0]\n")
sm = core.tuneup_apply_cmd()
check("allyhub-zram.service" not in sm and "vm.swappiness = 100" in sm,
      "SteamOS's own zram is left alone; only the swap settings are tuned")
_ta = core.TUNEUP_ZRAM_UNIT
core.TUNEUP_ZRAM_UNIT = str(fk / "zram-unit")
(fk / "zram-unit").write_text("x")
check(core.tuneup_applied(), "a half-finished apply still offers Undo")
core.TUNEUP_ZRAM_UNIT = _ta
check("performance" in core.PROFILE_KEYS and core.load_config()["performance"] == {"boost": False},
      "Game Boost setting is in the config (off by default) and in profiles")
# ---- every-game settings (environment.d, like Bazzite) ----
check(core.GAME_ENV_OPTIONS["fsr4"][0] == {"PROTON_FSR4_UPGRADE": "1"},
      "FSR 4 uses PROTON_FSR4_UPGRADE (the RDNA3-only variable is obsolete)")
check(not core.game_env_enabled("fsr4") and not core.GAME_ENV_FILE.exists(), "off by default, no file")
core.game_env_set("fsr4", True); core.game_env_set("fsr4_badge", True)
check(core.game_env_read() == {"PROTON_FSR4_UPGRADE": "1", "PROTON_FSR4_INDICATOR": "1"}
      and str(core.GAME_ENV_FILE).endswith(".config/environment.d/90-allyhub-games.conf"),
      "settings land in the user's environment.d file")
check(all(" " not in l and not l.startswith("export") for l in core.GAME_ENV_FILE.read_text().splitlines()
          if not l.startswith("#")), "plain KEY=VALUE lines, as systemd environment.d expects")
core.game_env_set("fsr4_badge", False)
check(core.game_env_enabled("fsr4") and not core.game_env_enabled("fsr4_badge"), "switches are independent")
check(core.game_env_live("fsr4", {"PROTON_FSR4_UPGRADE": "1"}) is True
      and core.game_env_live("fsr4", {}) is False, "tells whether Steam already has it")
_p = subprocess.Popen(["sleep", "5"], env=dict(os.environ, PROTON_FSR4_UPGRADE="1"))
time.sleep(0.2)
check(core.process_env(("sleep",)).get("PROTON_FSR4_UPGRADE") == "1", "reads a running process's environment")
_p.kill()
check(core.process_env(("no-such-proc",)) is None, "no Steam running -> unknown")
core.game_name = (lambda _orig: lambda a: "Ally Hub" if a == "999" else _orig(a))(core.game_name)
check(core.is_self_game("999") and not core.is_self_game("1240440") and not core.is_self_game(None),
      "Ally Hub opened from the library isn't treated as a game (no Game Boost for it)")
core.game_env_set("fsr4", False)
check(not core.GAME_ENV_FILE.exists(), "turning everything off removes the file")
ct = Path(HOME) / ".steam/root/compatibilitytools.d"
(ct / "GE-Proton10-30").mkdir(parents=True); (ct / "SomethingElse").mkdir()
check(core.custom_protons() == ["GE-Proton10-30"], "finds GE-Proton")
# ---- NonSteamLaunchers from Ally Hub's own page ----
check(core.nsl_install_cmd([]) is None and core.nsl_install_cmd(["rm -rf ~"]) is None, "only known launchers are passed")
nc = core.nsl_install_cmd(["Epic Games", "Youtube"], separate=True)
check(subprocess.run(["bash", "-n", "-c", nc]).returncode == 0, "launcher command parses")
nb = Path(HOME) / "nslbin"; nb.mkdir()
fake = nb / "nsl-src.sh"
fake.write_text('#!/bin/bash\necho "args: $*"\n( echo 10; echo "# Installing Epic Games"; echo 100 ) | zenity --progress --title=x\n'
                'if zenity --question --text="Restart Steam?"; then echo RESTARTED; fi\nexit 0\n')
(nb / "curl").write_text('#!/bin/sh\nwhile [ $# -gt 1 ]; do [ "$1" = -o ] && out=$2; shift; done\ncp ' + str(fake) + ' "$out"\n')
(nb / "curl").chmod(0o755)
r = subprocess.run(["bash", "-c", nc], env=dict(os.environ, PATH=f"{nb}:{os.environ['PATH']}"), capture_output=True, text=True)
check(r.returncode == 0 and "args: " + core.NSL_SEPARATE + " Epic Games Youtube" in r.stdout,
      "runs NonSteamLaunchers with the picked launchers: " + r.stdout[-200:] + r.stderr[-200:])
check("Installing Epic Games" in r.stdout, "its progress window becomes lines in the Activity log")
check("RESTARTED" not in r.stdout, "questions are answered no, so nothing surprising happens")
check(not core.nsl_installed("Epic Games"), "install state comes from the launcher's files")
ep = core.NSL_PREFIX / "Program Files/Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe"
ep.parent.mkdir(parents=True); ep.write_text("x")
check(core.nsl_installed("Epic Games") and not core.nsl_installed("Youtube"), "detects an installed store")
check(core.NSL_LOG.exists() and "Installing Epic Games" in core.NSL_LOG.read_text(), "the full run is kept for reports")
check("nslgamescanner" in nc and core.NSL_SCANNER.name in nc, "a fresh scan runs after installing, so the new launcher reaches Steam")
ud = Path(HOME) / ".steam/root/userdata/123/config"; ud.mkdir(parents=True)
(ud / "shortcuts.vdf").write_bytes(b"\x00shortcuts\x00\x000\x00\x02appid\x00\x01\x02\x03\x04\x01AppName\x00Epic Games\x00\x08\x08")
check("Epic Games" in core.steam_shortcut_names(), "reads Steam's shortcut names")
r = core.nsl_results(["Epic Games", "Battle.net", "Youtube"])
check(r == {"missing": ["Battle.net"], "no_shortcut": ["Youtube"]},
      "after a run: knows what didn't install and what isn't in Steam yet: " + str(r))
# ---- Launchers: the right Steam account, Steam's own API as a fallback, uninstall and leftovers ----
import threading as _th, socket as _so, base64 as _b64, re
cfgd = Path(HOME) / ".local/share/Steam/config"; cfgd.mkdir(parents=True, exist_ok=True)
(cfgd / "loginusers.vdf").write_text('"users"\n{\n\t"76561198000000001"\n\t{\n\t\t"AccountName"\t\t"old"\n\t\t"MostRecent"\t\t"0"\n\t\t"Timestamp"\t\t"100"\n\t}\n'
                                     '\t"76561198000000002"\n\t{\n\t\t"AccountName"\t\t"player"\n\t\t"MostRecent"\t\t"1"\n\t\t"Timestamp"\t\t"50"\n\t}\n}\n')
uid_new = str(76561198000000002 - 76561197960265728)
(Path(HOME) / ".steam/root/userdata" / uid_new / "config").mkdir(parents=True, exist_ok=True)
(Path(HOME) / ".steam/root/userdata" / str(76561198000000001 - 76561197960265728)).mkdir(parents=True, exist_ok=True)
check(core.steam_user_id3() == uid_new, "finds the signed-in Steam account from loginusers.vdf (MostRecent wins)")
core.NSL_ENV.parent.mkdir(parents=True, exist_ok=True)
core.NSL_ENV.write_text("export steamid3=-76561197960265728\nexport bnet_launcher=NonSteamLaunchers\n")
vdfp = core.shortcuts_vdf(uid_new)
r = subprocess.run(["bash", "-c", core._nsl_prep_shell(uid_new)], capture_output=True, text=True)
envt = core.NSL_ENV.read_text()
check(r.returncode == 0 and f"export steamid3={uid_new}" in envt and "-7656" not in envt and "bnet_launcher" in envt,
      "fixes the wrong Steam account in NonSteamLaunchers' settings: " + r.stderr[-200:])
check(vdfp.read_bytes() == b"\x00shortcuts\x00\x08\x08" and os.access(vdfp, os.X_OK),
      "creates a valid empty shortcuts.vdf the scanner won't wipe")
vdfp.write_bytes(b"\x00shortcuts\x00\x000\x00\x01AppName\x00Ally Hub\x00\x08\x08"); vdfp.chmod(0o644)
subprocess.run(["bash", "-c", core._nsl_prep_shell(uid_new)])
check(os.access(vdfp, os.X_OK) and b"Ally Hub" in vdfp.read_bytes() and (core.DATA_DIR / "shortcuts.vdf.bak").exists(),
      "keeps existing shortcuts (backed up, made executable so the scanner loads instead of wiping them)")
ic = core.nsl_install_cmd(["Youtube", "Battle.net"], id3=uid_new)
check("'Google Chrome'" in ic, "web picks also pass Google Chrome, or NSL builds broken web shortcuts")
check(ic.index("export steamid3") < ic.index("NSLGameScanner"), "the account is fixed before the scan runs")
check(subprocess.run(["bash", "-n", "-c", ic]).returncode == 0, "install command parses")
uc = core.nsl_uninstall_cmd(["Ubisoft Connect", "Youtube"])
check("'Uninstall Uplay'" in uc and "Youtube" not in uc and subprocess.run(["bash", "-n", "-c", uc]).returncode == 0,
      "uninstall uses NSL's own names (Ubisoft is 'Uplay'); web ones are just Steam tiles")
check(core.nsl_uninstall_cmd(["Youtube"]) is None, "nothing to run for web-only removals")
bn = core.NSL_PREFIX / "Program Files (x86)/Battle.net/Battle.net Launcher.exe"
bn.parent.mkdir(parents=True, exist_ok=True); bn.write_text("x")
sp = core.nsl_shortcut_spec("Battle.net")
check(sp and 'STEAM_COMPAT_DATA_PATH="' in sp["LaunchOptions"] and "compatdata/NonSteamLaunchers/\" %command%" in sp["LaunchOptions"]
      and sp["exe"].startswith('"') and sp["CompatTool"] == "GE-Proton10-30", "builds the same shortcut NSL would: " + str(sp))
wp = core.nsl_shortcut_spec("Youtube")
check(wp["exe"] == '"/usr/bin/flatpak"' and wp["LaunchOptions"].endswith("https://www.youtube.com"), "web shortcut opens Chrome")
check(core.nsl_shortcut_spec("Ubisoft Connect") is None, "no shortcut for a store that isn't installed")
# a fake Steam debugger: /json plus a websocket that answers Runtime.evaluate
seen = []
def _serve(srv):
    while True:
        try:
            c, _ = srv.accept()
        except OSError:
            return
        req = b""
        while b"\r\n\r\n" not in req:
            req += c.recv(4096)
        if req.startswith(b"GET /json"):
            body = json.dumps([{"title": "Other"}, {"title": "SharedJSContext",
                               "webSocketDebuggerUrl": f"ws://127.0.0.1:{srv.getsockname()[1]}/devtools/page/1"}]).encode()
            c.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n" % len(body) + body)
            c.close(); continue
        import hashlib as _h
        key = re.search(rb"Sec-WebSocket-Key: (\S+)", req).group(1)
        acc = _b64.b64encode(_h.sha1(key + b"258EAFA5-E914-47DA-95CA-C5AB0DC525B11").digest())
        c.sendall(b"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: " + acc + b"\r\n\r\n")
        b1, b2 = c.recv(2)
        n = b2 & 0x7F
        if n == 126: n = int.from_bytes(c.recv(2), "big")
        elif n == 127: n = int.from_bytes(c.recv(8), "big")
        mask = c.recv(4); data = b""
        while len(data) < n: data += c.recv(n - len(data))
        msg = json.loads(bytes(x ^ mask[i % 4] for i, x in enumerate(data)))
        expr = msg["params"]["expression"]; seen.append(expr)
        val = 2 if expr == "1+1" else json.dumps(["Battle.net"]) if "AddShortcut" in expr or "RemoveShortcut" in expr \
            else json.dumps(["Ally Hub", "Battle.net"])
        out = json.dumps({"method": "Runtime.consoleAPICalled", "params": {}}).encode()        # noise first
        c.sendall(bytes([0x81, len(out)]) + out if len(out) < 126 else bytes([0x81, 126]) + len(out).to_bytes(2, "big") + out)
        out = json.dumps({"id": msg["id"], "result": {"result": {"type": "string", "value": val}}}).encode()
        c.sendall(bytes([0x81, 126]) + len(out).to_bytes(2, "big") + out if len(out) > 125 else bytes([0x81, len(out)]) + out)
        c.close()
srv = _so.socket(); srv.bind(("127.0.0.1", 0)); srv.listen(5)
_th.Thread(target=_serve, args=(srv,), daemon=True).start()
core.CEF_PORT = srv.getsockname()[1]
check(core.cef_eval("1+1") == 2, "talks to Steam's debugger over a websocket (standard library only)")
check(core.cef_shortcut_names() == {"Ally Hub", "Battle.net"}, "reads the library's shortcuts live")
check(core.cef_add_shortcuts(["Battle.net"]) == ["Battle.net"] and "SteamClient.Apps.AddShortcut" in seen[-1]
      and "STEAM_COMPAT_DATA_PATH" in seen[-1], "adds a missing tile through Steam itself")
check(core.cef_remove_shortcuts(["Battle.net"]) == ["Battle.net"] and "RemoveShortcut" in seen[-1], "removes tiles on uninstall")
check(core.nsl_results(["Battle.net"], core.cef_shortcut_names()) == {"missing": [], "no_shortcut": []},
      "checks the live library, not a stale file")
srv.close(); core.CEF_PORT = 1
check(core.cef_eval("1+1") is None and core.cef_add_shortcuts(["Battle.net"]) is None,
      "debugger off: says so instead of hanging or crashing")
# leftovers
own = core.COMPATDATA / "EpicGamesLauncher" / "pfx/drive_c"; own.mkdir(parents=True)
core.NSL_DOWNLOADS.mkdir(parents=True)
lo = {str(i["path"]): i for i in core.nsl_leftovers()}
check(str(core.COMPATDATA / "EpicGamesLauncher") in lo and str(core.NSL_DOWNLOADS) in lo,
      "finds an empty old prefix and installer downloads")
check(str(core.COMPATDATA / "NonSteamLaunchers") not in lo, "never offers the shared prefix while a store is still in it")
check(not any("NSLGameScanner" in p for p in lo), "keeps the game scanner while launchers are installed")
cc = core.nsl_clean_cmd([core.COMPATDATA / "EpicGamesLauncher", Path("/etc/passwd"), Path(HOME), core.NSL_DOWNLOADS])
check("/etc/passwd" not in cc and f"'{HOME}'" not in cc and "EpicGamesLauncher" in cc, "cleaner only deletes known leftovers in your home folder")
subprocess.run(["bash", "-c", cc])
check(not (core.COMPATDATA / "EpicGamesLauncher").exists() and not core.NSL_DOWNLOADS.exists() and bn.exists(),
      "cleaner deletes the leftovers and nothing else")
check(core.nsl_clean_cmd([Path("/etc/x")]) is None, "nothing safe to delete -> no command")
# ---- library art: icons out of .exe files, art drawn as SVG, handed to Steam ----
import struct as _st, xml.etree.ElementTree as _ET
def _fake_exe(images):
    # a minimal PE32 with one icon group holding images [(width_byte, bpp, bytes)]
    ids = list(range(1, len(images) + 1))
    grp = _st.pack("<HHH", 0, 1, len(images)) + b"".join(
        _st.pack("<BBBBHHIH", w, w, 0, 0, 1, bpp, len(img), i) for (w, bpp, img), i in zip(images, ids))
    blobs = [img for _w, _b, img in images] + [grp]
    # layout inside .rsrc: root dir, type dirs, name dirs, lang dirs, data entries, then blobs
    def d(n): return _st.pack("<IIHHHH", 0, 0, 0, 0, 0, n)
    root, t3, t14 = 0, 16 + 16, 0
    t3 = 16 + 8 * 2
    t14 = t3 + 16 + 8 * len(ids)
    names_start = t14 + 16 + 8
    lang = [names_start + k * (16 + 8) for k in range(len(blobs))]
    data_e = lang[-1] + 24
    blob_off = data_e + 16 * len(blobs)
    rs = bytearray()
    rs += d(2) + _st.pack("<II", 3, 0x80000000 | t3) + _st.pack("<II", 14, 0x80000000 | t14)
    rs += d(len(ids)) + b"".join(_st.pack("<II", i, 0x80000000 | lang[k]) for k, i in enumerate(ids))
    rs += d(1) + _st.pack("<II", 1, 0x80000000 | lang[-1])
    for k in range(len(blobs)):
        rs += d(1) + _st.pack("<II", 1033, data_e + 16 * k)
    pos = blob_off
    for b in blobs:
        rs += _st.pack("<IIII", 0x1000 + pos, len(b), 0, 0); pos += len(b)
    for b in blobs:
        rs += b
    hdr = bytearray(0x200)
    hdr[0:2] = b"MZ"; hdr[0x3C:0x40] = _st.pack("<I", 0x40)
    hdr[0x40:0x44] = b"PE\0\0"
    hdr[0x44:0x58] = _st.pack("<HHIIIHH", 0x14C, 1, 0, 0, 0, 0xE0, 0x102)
    opt = 0x58
    hdr[opt:opt + 2] = _st.pack("<H", 0x10B)
    hdr[opt + 96 + 16:opt + 96 + 24] = _st.pack("<II", 0x1000, len(rs))
    sec = opt + 0xE0
    hdr[sec:sec + 40] = b".rsrc\0\0\0" + _st.pack("<IIIIIIHHI", len(rs), 0x1000, len(rs), 0x200, 0, 0, 0, 0, 0)
    return bytes(hdr) + bytes(rs)
_png2 = core._png_encode(2, 2, bytes([0, 0, 255, 255] * 4))
_dib = _st.pack("<IiiHHIIiiII", 40, 4, 8, 1, 32, 0, 0, 0, 0, 0, 0) + bytes([255, 0, 0, 255] * 16) + bytes(4 * 4)
_exe = Path(HOME) / "Battle.net Launcher.exe"
_exe.write_bytes(_fake_exe([(32, 32, _dib), (0, 32, _png2)]))
ents = core.pe_icon_entries(_exe.read_bytes())
check([e[0] for e in ents] == [256, 32], "finds every image of the program's icon, biggest first: " + str([e[:2] for e in ents]))
check(core.exe_icon_png(_exe) == _png2, "uses the program's own 256 px icon as is")
_exe2 = Path(HOME) / "old.exe"; _exe2.write_bytes(_fake_exe([(4, 32, _dib)]))
px = core._png_pixels(core.exe_icon_png(_exe2) or b"")
check(px and px[:2] == (4, 4) and px[2][:4] == bytes([0, 0, 255, 255]), "turns a classic icon bitmap into a PNG (BGRA -> RGBA)")
check(core.exe_icon_png(Path(HOME) / "missing.exe") is None and core.pe_icon_entries(b"MZ junk") == [],
      "a missing or broken program just has no icon")
check(core.icon_color(_png2).startswith("#") and int(core.icon_color(_png2)[5:7], 16) > 150, "picks the icon's color for the background")
check(core.icon_color(None) == core.ART_FALLBACK_COLOR, "no icon -> a calm default color")
arts = core.art_svgs("Tom & Jerry's <Launcher>", _png2)
check(set(arts) == {"portrait", "wide", "hero", "logo"} and arts["portrait"][1:] == (600, 900),
      "makes a tall cover, wide banner, hero and logo")
for k, (svg, w, h) in arts.items():
    _ET.fromstring(svg)
check("Tom &amp; Jerry" in arts["portrait"][0] and "data:image/png;base64," in arts["wide"][0], "names are escaped and the icon is embedded")
check("filter" not in "".join(a[0] for a in arts.values()), "only SVG features Qt can draw")
g = core.art_svgs("Netflix", None, "#e11d48", '<circle cx="12" cy="12" r="10" />')
check("icon" in g and "circle" in g["icon"][0], "no icon of its own -> a drawn icon tile too")
sz, lines = core._wrap_title("Rockstar Games Launcher", 520, 66)
check(len(lines) <= 2 and all(len(l) * sz * 0.56 <= 520 for l in lines), "long names wrap to fit")
# shortcuts.vdf reader and the plan
_vdf = (b"\x00shortcuts\x00\x000\x00\x02appid\x00" + (3123456789).to_bytes(4, "little") + b"\x01AppName\x00Battle.net\x00"
        b"\x01Exe\x00\"" + str(_exe).encode() + b"\"\x00\x01icon\x00\x00\x08"
        b"\x001\x00\x02appid\x00" + (2900000001).to_bytes(4, "little") + b"\x01AppName\x00Ally Hub\x00"
        b"\x01Exe\x00\"/home/deck/.local/bin/allyhub\"\x00\x08\x08\x08")
core.shortcuts_vdf().write_bytes(_vdf)
_cef = core.cef_eval
core.cef_eval = lambda js, timeout=20, port=None: None
sc = core.steam_shortcuts()
check([(s["appid"], s["name"]) for s in sc] == [(3123456789, "Battle.net"), (2900000001, "Ally Hub")],
      "reads tiles and their ids from shortcuts.vdf: " + str(sc))
plan = core.art_plan()
check([t["name"] for t in plan["todo"]] == ["Battle.net", "Ally Hub"] and plan["todo"][0]["icon_png"] == _png2
      and plan["todo"][1]["self"], "blank tiles get art, with each program's own icon")
check([t["name"] for t in core.art_plan(only=["battle.net"])["todo"]] == ["Battle.net"], "after an install: only the new tiles")
sent = []
core.cef_eval = lambda js, timeout=20, port=None: (sent.append(js), '[0, 3, "icon"]')[1]
res = core.apply_art(3123456789, {"portrait": b"P", "wide": b"W", "hero": b"H", "logo": b"L"}, _png2, "Battle.net")
grid = core.steam_grid_dir()
check(res["live"] and res["files"] == 4 and (grid / "3123456789p.png").read_bytes() == b"P"
      and (grid / "3123456789.png").exists() and (grid / "3123456789_hero.png").exists() and (grid / "3123456789_logo.png").exists(),
      "saves the art in Steam's grid folder and hands it over live")
check(sent and "SetCustomArtworkForApp(id" in sent[0] and "3123456789" in sent[0] and "SetShortcutIcon" in sent[0]
      and (core.ART_DIR / "3123456789_icon.png").read_bytes() == _png2, "sets the icon from the program's own icon file")
check([t["name"] for t in core.art_plan()["todo"]] == ["Ally Hub"], "tiles with art are left alone")
(grid / "2900000001p.jpg").write_bytes(b"mine")
p2 = core.art_plan(redo=True)
check([t["name"] for t in p2["todo"]] == ["Battle.net"] and p2["ours"] == 1,
      "remaking only ever touches art Ally Hub made, never the owner's own")
core.cef_eval = lambda js, timeout=20, port=None: None
res = core.apply_art(2900000001, {"portrait": b"P", "hero": b"H"}, None, "Ally Hub")
check(res["files"] == 1 and (grid / "2900000001p.jpg").read_bytes() == b"mine" and (grid / "2900000001_hero.png").exists(),
      "a picture the owner set stays, kind by kind; the rest still gets art")
res = core.apply_art(555, {"portrait": b"P"}, None, "New")
check(not res["live"] and res["files"] == 1, "without Steam's connection the art is saved for the next Steam start")
(grid / "3123456789_logo.png").write_bytes(b"from SteamGridDB")
core.apply_art(3123456789, {"portrait": b"P2", "logo": b"L2"}, None, "Battle.net")
check((grid / "3123456789_logo.png").read_bytes() == b"from SteamGridDB" and (grid / "3123456789p.png").read_bytes() == b"P2",
      "art replaced after Ally Hub made it is no longer treated as Ally Hub's")
core.apply_art(3123456789, {"portrait": b"MY PHOTO"}, None, "Battle.net", mine=True)
check((grid / "3123456789p.png").read_bytes() == b"MY PHOTO" and "3123456789" not in core.art_made()
      and not core.art_is_ours(3123456789, "portrait"), "the owner's own picture goes in and is never remade")
check(core.art_plan(redo=True)["todo"] == [], "remake leaves the owner's pictures alone")
core.cef_eval = _cef
_payload = "x" * 300000
import socket as _so2
a, b = _so2.socketpair()
_th.Thread(target=core._ws_send, args=(a, _payload)).start()
hdr = core._recv_exact(b, 2); n = int.from_bytes(core._recv_exact(b, 8), "big"); m = core._recv_exact(b, 4)
body = core._recv_exact(b, n)
check(bytes(c ^ m[i % 4] for i, c in enumerate(body)).decode() == _payload, "big messages to Steam are masked correctly")
a.close(); b.close()
# ---- Storage saver: leftovers of removed games, unused Proton builds, the trash ----
sa = core.STEAM_ROOT / "steamapps"
(sa / "appmanifest_100.acf").write_text('"AppState"\n{\n\t"appid"\t\t"100"\n\t"name"\t\t"Big Game"\n\t"installdir"\t\t"Big Game"\n\t"SizeOnDisk"\t\t"5000000"\n}\n')
(sa / "common/Big Game").mkdir(parents=True, exist_ok=True)
def _blob(p, n):
    p.mkdir(parents=True, exist_ok=True); (p / "f.bin").write_bytes(b"x" * n)
_blob(sa / "shadercache/100", 3000); _blob(sa / "compatdata/100", 4000)
_blob(sa / "shadercache/200", 2000); _blob(sa / "compatdata/200/pfx", 6000)
_blob(sa / "compatdata/3123456789", 1000)          # the Battle.net tile from the art tests: in use
_blob(sa / "downloading/300", 7000); _blob(sa / "downloading/100", 500)
_tools = core.STEAM_ROOT / "compatibilitytools.d"
for n in ("GE-Proton8-1", "GE-Proton9-27", "GE-Proton99-1"):
    _blob(_tools / n, 1500)
(core.STEAM_ROOT / "config").mkdir(parents=True, exist_ok=True)
(core.STEAM_ROOT / "config/config.vdf").write_text('"InstallConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n'
    '\t\t\t\t"CompatToolMapping"\n\t\t\t\t{\n\t\t\t\t\t"555"\n\t\t\t\t\t{\n\t\t\t\t\t\t"name"\t\t"GE-Proton8-1"\n\t\t\t\t\t}\n\t\t\t\t}\n'
    '\t\t\t\t"Other"\t\t"1"\n\t\t\t}\n\t\t}\n\t}\n}\n')
_blob(core.TRASH_DIR / "files", 2 * 1024 * 1024)
check(core.compat_tools_in_use() == {"GE-Proton8-1"}, "knows which Proton builds Steam uses")
check([a["name"] for a in core.steam_apps()] == ["Big Game"], "lists installed Steam games from their manifests")
_cef = core.cef_eval
core.cef_eval = lambda js, timeout=20, port=None: '[["200","Old Game"],["300",""]]' if "GetAppOverviewByAppID" in js else None
res = core.storage_scan()
core.cef_eval = _cef
labels = {i["label"]: i for i in res["items"]}
g = res["games"][0]
check(g["name"] == "Big Game" and g["shaders"] == 3000 and g["prefix"] == 4000 and g["total"] == 5007000,
      "each game's size includes its shader cache and Windows files: " + str({k: g[k] for k in ("shaders", "prefix", "total")}))
check(labels.get("Shader cache of Old Game", {}).get("group") == "safe", "a removed game's shader cache can go (named from Steam's library)")
check(labels.get("Windows files of Old Game", {}).get("group") == "check" and labels["Windows files of Old Game"]["warn"],
      "a removed game's Windows files start unticked: they can hold saves")
check(labels.get("Unfinished download of a removed game (app 300)", {}).get("group") == "safe", "abandoned downloads can go")
check(labels.get("Unfinished update for Big Game", {}).get("group") == "check", "a pending update is offered but unticked")
check(not any("3123456789" in str(i["path"]) for i in res["items"]), "non-Steam tiles' files are never leftovers")
check(any(i["label"].startswith("GE-Proton9-27") for i in res["items"]) and
      not any(i["label"].startswith(("GE-Proton8-1", "GE-Proton99-1")) for i in res["items"]),
      "offers only Proton builds no game uses, and keeps the newest of each kind")
check("Desktop Mode trash" in labels and res["drives"] and res["drives"][0]["label"] == "Internal storage", "trash and drives")
paths = [i["path"] for i in res["items"]]
cmd = core.storage_clean_cmd(paths + [sa / "common/Big Game", Path("/etc"), Path(HOME) / "Documents", sa / "compatdata/../.."])
check(cmd and "Big Game" not in cmd and "/etc" not in cmd and "Documents" not in cmd and "/.." not in cmd,
      "cleanup only ever deletes the kinds of folders the scan offers, never a game: " + str(cmd)[:200])
subprocess.run(["bash", "-c", cmd])
check(not (sa / "shadercache/200").exists() and not (sa / "downloading/300").exists() and (sa / "common/Big Game").exists()
      and (sa / "shadercache/100").exists() and (core.TRASH_DIR / "files").exists() and not any((core.TRASH_DIR / "files").iterdir())
      and (_tools / "GE-Proton8-1").exists() and not (_tools / "GE-Proton9-27").exists(), "deletes what was picked and nothing else")
check(core.storage_clean_cmd([Path("/")]) is None, "nothing safe picked -> no command")
(core.STEAM_ROOT / "config/config.vdf").write_text('"InstallConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n'
    '\t\t\t\t"CompatToolMapping"\n\t\t\t\t{\n\t\t\t\t\t"0"\n\t\t\t\t\t{\n\t\t\t\t\t\t"name"\t\t"proton_9"\n\t\t\t\t\t}\n'
    '\t\t\t\t\t"1245620"\n\t\t\t\t\t{\n\t\t\t\t\t\t"name"\t\t"GE-Proton9-20"\n\t\t\t\t\t}\n'
    '\t\t\t\t\t"777"\n\t\t\t\t\t{\n\t\t\t\t\t\t"name"\t\t"Custom-Internal-Id"\n\t\t\t\t\t}\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n')
check(core.compat_tools_in_use() == {"proton_9", "GE-Proton9-20", "Custom-Internal-Id"}, "reads every Proton choice, not just the first")
for n in ("GE-Proton9-20", "my-folder"):
    _blob(_tools / n, 100)
(_tools / "my-folder/compatibilitytool.vdf").write_text('"compatibilitytools"\n{\n "compat_tools"\n {\n  "Custom-Internal-Id"\n  {\n   "install_path" "."\n  }\n }\n}\n')
_blob(_tools / "linked-target", 100); (_tools / "latest").symlink_to(_tools / "linked-target")
inuse = core.tools_in_use_folders()
check((_tools / "GE-Proton9-20").resolve() in inuse and (_tools / "my-folder").resolve() in inuse
      and (_tools / "linked-target").resolve() in inuse, "a Proton in use is known by folder, internal id or symlink")
check(core.storage_clean_cmd([_tools / "GE-Proton9-20", _tools / "my-folder", _tools / "linked-target", _tools / "latest"]) is None,
      "Proton builds in use are never deleted, even from an old scan")
_blob(sa / "compatdata/100", 10)
check(core.storage_clean_cmd([sa / "compatdata/100", sa / "compatdata/3123456789"]) is None,
      "an installed game's or a non-Steam tile's Windows files are never deleted")
(sa / "libraryfolders.vdf").write_text('"libraryfolders"\n{\n\t"1"\n\t{\n\t\t"path"\t\t"/run/media/deck/SD"\n\t\t"apps"\n\t\t{\n\t\t\t"4242"\t\t"1"\n\t\t}\n\t}\n}\n')
_blob(sa / "compatdata/4242", 10)
check("4242" in core.library_app_ids() and core.storage_clean_cmd([sa / "compatdata/4242"]) is None,
      "games on an SD card that isn't inserted still count as installed")
(sa / "libraryfolders.vdf").unlink()
_blob(sa / "shadercache/100", 10)
c = core.storage_clean_cmd([sa / "shadercache/100"])
check(c and "exit $rc" in c and subprocess.run(["bash", "-c", c]).returncode == 0, "clearing a shader cache reports real success")
# ---- Game settings: launch options as switches, Proton picker, rescue ----
check(core.launch_flags("PROTON_LOG=1 mangohud %command% -dx11") == {"log"}, "reads which switches are on")
check(core.set_launch_flags("PROTON_LOG=1 mangohud %command% -dx11", {"fsr4", "lsfg"})
      == "PROTON_FSR4_UPGRADE=1 mangohud ~/lsfg %command% -dx11", "switches go in, the owner's own options stay")
check(core.set_launch_flags("-dx11", {"fsr4"}) == "PROTON_FSR4_UPGRADE=1 %command% -dx11", "plain game arguments get %command%")
check(core.set_launch_flags("PROTON_FSR4_UPGRADE=1 %command%", set()) == "", "turning the last switch off leaves nothing behind")
check(core.set_launch_flags("PROTON_FSR4_UPGRADE=1 %command% -skip", set()) == "%command% -skip", "game arguments survive")
q = 'WINEDLLOVERRIDES="dxgi=n,b" %command%'
check(core.set_launch_flags(q, {"deck"}) == 'SteamDeck=1 WINEDLLOVERRIDES="dxgi=n,b" %command%', "quoted values are kept whole")
check(core.launch_flags(core.set_launch_flags("", set(core.GAME_TOGGLES))) == set(core.GAME_TOGGLES), "every switch round-trips")
check(core.launch_flags(f"{HOME}/lsfg %command%") == {"lsfg"}, "frame generation is found by its full path too")
check(not core.launch_parseable("--name=Don't %command%") and not core.launch_parseable('bash -c "echo; %command%"')
      and core.launch_parseable('A="b c" %command% -x') and core.launch_parseable("-dx11"), "spots launch options the switches can't edit safely")
check(core.set_launch_flags("SteamDeck=0 PROTON_LOG=2 %command%", set()) == "SteamDeck=0 PROTON_LOG=2 %command%",
      "the owner's own values of the same variables are left alone")
check(core.set_launch_flags("SteamDeck=0 %command%", {"deck"}) == "SteamDeck=1 %command%", "turning a switch on replaces its variable")
check(core.steam_appid_of(str((7 << 32) | 0x02000000)) == 7 and core.steam_appid_of("1240440") == 1240440
      and core.steam_appid_of(None) is None, "running non-Steam games map to their tile")
t = core.parse_vdf_text('"a"\n{\n\t"b"\t\t"x \\"y\\""\n\t"c"\n\t{\n\t\t"d"\t\t"1"\n\t}\n}\n')
check(t == {"a": {"b": 'x "y"', "c": {"d": "1"}}}, "reads Steam's text files: " + str(t))
lc = Path(HOME) / ".steam/root/userdata" / core.steam_user_id3() / "config/localconfig.vdf"
lc.write_text('"UserLocalConfigStore"\n{\n\t"Software"\n\t{\n\t\t"Valve"\n\t\t{\n\t\t\t"Steam"\n\t\t\t{\n\t\t\t\t"apps"\n\t\t\t\t{\n'
              '\t\t\t\t\t"100"\n\t\t\t\t\t{\n\t\t\t\t\t\t"LastPlayed"\t\t"1700000000"\n\t\t\t\t\t\t"LaunchOptions"\t\t"PROTON_LOG=1 %command%"\n\t\t\t\t\t}\n'
              '\t\t\t\t}\n\t\t\t}\n\t\t}\n\t}\n}\n')
(sa / "appmanifest_1493710.acf").write_text('"AppState"\n{\n\t"appid"\t\t"1493710"\n\t"name"\t\t"Proton Experimental"\n\t"installdir"\t\t"Proton - Experimental"\n}\n')
gc = core.game_choices()
check([g["name"] for g in gc][:1] == ["Big Game"] and "Proton Experimental" not in [g["name"] for g in gc]
      and "Ally Hub" not in [g["name"] for g in gc] and any(g["kind"] == "shortcut" for g in gc),
      "lists games (recently played first) and non-Steam tiles, not Proton or Ally Hub: " + str([g["name"] for g in gc]))
_cef = core.cef_eval
core.cef_eval = lambda js, timeout=20, port=None: None
st = core.game_settings(100)
check(st == {"options": "PROTON_LOG=1 %command%", "tool": "", "tools": [], "live": False}, "Steam's debugger off: reads the files, can't save: " + str(st))
core.cef_eval = lambda js, timeout=20, port=None: json.dumps({"found": True, "options": "SteamDeck=1 %command%", "tool": "GE-Proton9-27",
                                                              "tools": [["GE-Proton9-27", "GE-Proton9-27"], ["proton_experimental", "Proton Experimental"]]})
st = core.game_settings(100)
check(st["live"] and st["tool"] == "GE-Proton9-27" and ("proton_experimental", "Proton Experimental") in st["tools"], "reads live settings from Steam")
sent = []
core.cef_eval = lambda js, timeout=20, port=None: (sent.append(js), '["options", "tool"]')[1]
done = core.apply_game_settings(100, 'A="b c" %command%', "proton_experimental")
check(done == ["options", "tool"] and 'SetAppLaunchOptions(id, opts)' in sent[0] and '"A=\\"b c\\" %command%"' in sent[0]
      and "SpecifyCompatTool" in sent[0], "hands launch options and Proton to Steam, safely quoted")
core.apply_game_settings(100, "", None)
check("const id = 100, opts = \"\", tool = null" in sent[-1], "Proton left alone when it didn't change")
core.cef_eval = _cef
cmd = core.reset_prefix_cmd(100)
subprocess.run(["bash", "-c", cmd])
bk = [d for d in (sa / "compatdata").iterdir() if d.name.startswith("100_allyhub_backup_")]
check(not (sa / "compatdata/100").exists() and len(bk) == 1 and (bk[0] / "f.bin").exists(), "reset moves the Windows files aside, never deletes")
core.cef_eval = lambda js, timeout=20, port=None: None
items = core.storage_scan()["items"]
core.cef_eval = _cef
check(any(i["label"].startswith("Old Windows files of Big Game") and i["group"] == "check" for i in items),
      "Storage offers the set-aside folder later, unticked")
check(core.storage_clean_cmd([bk[0]]) and core.reset_prefix_cmd(424242) is None, "the backup can be cleared; no prefix, no reset")
(Path(HOME) / "steam-100.log").write_text("err: missing d3dx9_43.dll\n")
check("d3dx9_43" in core.proton_log(100) and core.proton_log(5) == "", "reads Proton's log for the report")
# ---- Quick Access panel: the Decky plugin Ally Hub installs ----
import py_compile as _pc, shutil as _sh
qf = core.qam_files()
_qd = Path(HOME) / "qam-check"; _qd.mkdir()
(_qd / "main.py").write_text(qf["main.py"]); _pc.compile(str(_qd / "main.py"), doraise=True)
_pkg, _pj = json.loads(qf["package.json"]), json.loads(qf["plugin.json"])
check(_pkg["version"] == core.QAM_VERSION and _pkg["type"] == "module" and _pj["api_version"] == 1 and not _pj["flags"],
      "panel files: ES module (Decky's modern loader), API 1, runs as the user (no root flag)")
check(f'connect(2, "{_pj["name"]}")' in qf["dist/index.js"], "the panel's frontend and backend use the same plugin name")
check("socket" not in qf["dist/index.js"] and "fetch(" not in qf["dist/index.js"] and "urllib" not in qf["main.py"]
      and "http" not in qf["main.py"], "the panel never talks to the network, only the local agent")
check(core.qam_installed() is None, "panel not installed yet")
qc = core.qam_install_cmd()
check(all((core.QAM_STAGE / n).exists() for n in qf) and "plugin_loader" in qc and str(core.QAM_DIR) in qc,
      "install stages the files and restarts Decky")
core.QAM_DIR.mkdir(parents=True); (core.QAM_DIR / "package.json").write_text('{"version": "0.9.0"}')
check(core.qam_installed() == "0.9.0", "knows the installed panel's version (for updates)")
_sh.rmtree(core.QAM_DIR)
if shutil.which("node"):
    harness = Path(HOME) / "qam-harness.mjs"
    (_qd / "index.js").write_text(qf["dist/index.js"])
    harness.write_text('''
const calls = [];
let STATE = [];
const named = (k) => ({ [k]: function () {} })[k];
const el = (t, p, ...c) => ({ t: typeof t === "function" ? t.name : t, f: typeof t === "function" ? t : null, p: p || {}, c });
globalThis.window = {
  SP_REACT: { createElement: el, useState: (v) => [STATE.length ? STATE.shift() : v, () => {}],
              useEffect: () => {}, useRef: () => ({ current: null }) },
  DFL: new Proxy({}, { get: (o, k) => k === "staticClasses" ? { Title: "t" } : named(String(k)) }),
  __DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit: {
    connect: (v, name) => { calls.push([v, name]); return { call: async () => ({}), toaster: { toast() {} } }; } },
};
const mod = await import(process.argv[2]);
const plugin = mod.default();
const render = (s) => { STATE = [s, null]; return plugin.content.f(plugin.content.p); };
const labels = (n, out = []) => {
  if (n && typeof n === "object") {
    if (n.p && n.p.label) out.push(n.t + ":" + n.p.label + (n.p.checked ? "=on" : ""));
    if (n.p && n.p.title) out.push("section:" + n.p.title);
    if (n.t === "ButtonItem") out.push("button:" + n.c.join(""));
    (n.c || []).forEach((x) => labels(x, out));
  }
  return out;
};
const full = { battery: "80%", time_left: "2 h", watts: 12, cpu: 60, gpu: 55, fan: 3000, game: "1", game_name: "Halo",
  game_flags: ["fsr4"], game_live: true, lsfg: false, boost: true, boost_note: "performance", lighting: "allyhub",
  effects: ["Aurora"], effect: "Aurora", brightness: 255, backup: true, backup_running: false };
console.log(JSON.stringify({ name: plugin.name, connect: calls[0], icon: plugin.icon.t,
  loading: labels(render(null)), error: labels(render({ error: "agent" })), full: labels(render(full)),
  shelved: labels(render({ battery: "80%", lighting: "huesync", game: null, backup: false })) }));
''')
    r = subprocess.run(["node", str(harness), str(_qd / "index.js")], capture_output=True, text=True, timeout=30)
    out = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
    check(out.get("name") == "Ally Hub" and out.get("connect") == [2, "Ally Hub"] and out.get("icon") == "Icon",
          "the panel loads in a Decky-like page and registers itself: " + (r.stderr[-400:] or str(out)))
    check(any("isn't running" in x for x in out["error"]), "agent off: the panel says how to turn it on")
    full = out["full"]
    check("ToggleField:FSR 4 upgrade=on" in full and "ToggleField:Steam Deck mode" in full
          and not any("Frame generation" in x for x in full), "this game's switches, frame gen only when installed: " + str(full))
    check("ToggleField:Game Boost=on" in full and "DropdownItem:Effect" in full and "SliderField:Brightness" in full
          and "button:Back up saves now" in full, "Game Boost, lighting and save backup controls")
    check("section:Lighting" not in out["shelved"] and "section:This game" not in out["shelved"],
          "no lighting controls while HueSync runs the rings, no game section without a game")
# ---- turning Decky plugins off without uninstalling ----
_ds = Path(HOME) / "decky-settings/loader.json"
_ds.parent.mkdir(parents=True); _ds.write_text('{"developer.enabled": true, "disabled_plugins": ["Old"]}')
for mode, names in (("off", ["HueSync", "Ally Hub"]), ("on", ["Ally Hub"])):
    subprocess.run(["python3", "-c", core._DECKY_TOGGLE_PY, str(_ds), mode, json.dumps(names)], check=True)
_dj = json.loads(_ds.read_text())
check(_dj["disabled_plugins"] == ["Old", "HueSync"] and _dj["developer.enabled"] is True,
      "Decky's off list gains and loses plugins, its other settings stay")
core.DECKY_SETTINGS = _ds
check(core.decky_disabled() == {"Old", "HueSync"}, "reads which plugins are off")
import shlex
_tc = core.decky_toggle_cmd(["x'; rm -rf ~; '"], True)
check("plugin_loader" in _tc and "x'; rm -rf ~; '" in shlex.split(_tc.split("python3 -c ", 1)[1])[3],
      "plugin names are passed safely: " + _tc[-160:])
check(core.decky_toggle_cmd([], True) is None, "nothing to toggle -> no command")
_st = {"decky": {"allycenter": {"dir": "/h/homebrew/plugins/AllyCenter", "name": "Ally Center", "version": "1"}}}
check(core.decky_item_names(core.CATALOG_BY_ID["allycenter"], _st) == ["Ally Center"], "finds the Decky name behind a catalog card")
check("decky_off" in core.gather_state(), "the app knows which plugins are off")
check("EmuDeck/backend/uninstall.sh" in core.CATALOG_BY_ID["emudeck"].uninstall, "EmuDeck can be removed with its own uninstaller")
core.EMUDECK_PATH.parent.mkdir(parents=True, exist_ok=True); core.EMUDECK_PATH.write_text("app")
_r = subprocess.run(["bash", "-c", core.emudeck_uninstall_cmd()], capture_output=True, text=True)
check(_r.returncode == 0 and not core.EMUDECK_PATH.exists() and "never set up" in _r.stdout,
      "EmuDeck that was never set up is removed cleanly (no missing-uninstaller error)")
# ---- Save time machine (Ludusavi stand-in on PATH) ----
_fb = Path(HOME) / "fakebin"; _fb.mkdir(exist_ok=True)
(_fb / "flatpak").write_text('''#!/usr/bin/env python3
import sys, json, os
log = os.path.join(os.environ["HOME"], "flatpak.log")
open(log, "a").write(json.dumps(sys.argv[1:]) + "\\n")
a = sys.argv[1:]
if a[0] == "info":
    sys.exit(0)
a = a[2:]
if a[0] == "find":
    if "--steam-id" in a:
        print(json.dumps({"games": {"Big Game": {}}} if a[a.index("--steam-id") + 1] == "100" else {"games": {}}))
        sys.exit(0 if a[a.index("--steam-id") + 1] == "100" else 1)
    print(json.dumps({"games": {"Battle.net Thing": {}}})); sys.exit(0)
if a[0] == "backups":
    print(json.dumps({"games": {"Big Game": {"backupPath": "x", "backups": [
        {"name": "backup-1", "when": "2026-10-01T10:00:00Z", "locked": False},
        {"name": "backup-2", "when": "2026-10-03T10:00:00Z", "locked": False}]}}}))
    sys.exit(0)
print(json.dumps({"overall": {}, "games": {}})); sys.exit(0)
''')
(_fb / "flatpak").chmod(0o755)
os.environ["PATH"] = str(_fb) + os.pathsep + os.environ["PATH"]
_flog = Path(HOME) / "flatpak.log"
check(core.ludusavi_ready(), "sees Ludusavi")
check(core.ludusavi_title(100, "Big Game") == "Big Game" and core.ludusavi_title(100) == "Big Game"
      and sum(1 for l in _flog.read_text().splitlines() if '"find"' in l) == 1, "finds a game's Ludusavi title by Steam id, once")
check(core.ludusavi_title(None, "Battle.net") == "Battle.net Thing" and core.ludusavi_title(555) == "", "by name for non-Steam games; unknown games are skipped")
check("steam:555" not in core.read_json(core.TM_TITLES, {}), "a lookup without a clear answer is tried again later")
check(core.ludusavi_title_cached(100) == "Big Game" and core.ludusavi_title_cached(None, "nope") == "", "cached titles for quick checks")
ba = core.tm_backup_args("Big Game", 5)
check(ba[-1] == "Big Game" and "--full-limit" in ba and ba[ba.index("--full-limit") + 1] == "5" and "--no-cloud-sync" in ba
      and str(core.TM_DIR) in ba, "snapshots go to their own folder with Ludusavi keeping the newest few")
core.TM_DIR.mkdir(parents=True, exist_ok=True)
sn = core.tm_snapshots()
check(list(sn) == ["Big Game"] and sn["Big Game"][0]["name"] == "backup-2", "lists snapshots per game, newest first")
_r = subprocess.run(["bash", "-c", core.tm_restore_cmd("Big Game", "backup-1")], capture_output=True, text=True)
calls = [json.loads(l) for l in _flog.read_text().splitlines()][-2:]
_rc = core.tm_restore_cmd("Big Game", "b")
check("'Big Game' && flatpak run com.github.mtkennerly.ludusavi restore" in _rc and ">/dev/null" not in _rc,
      "the restore only runs if saving the current saves worked, and its output is kept")
_ru = core.tm_restore_cmd("Big Game", "u1", undo=True)
check(str(core.TM_BEFORE_RESTORE) in _ru and "u1" in _ru and " backup " not in _ru, "undo restores the safety copy")
check(_r.returncode == 0 and "Restored Big Game" in _r.stdout and "backup" in calls[0] and str(core.TM_BEFORE_RESTORE) in calls[0]
      and "restore" in calls[1] and calls[1][calls[1].index("--backup") + 1] == "backup-1",
      "a restore saves what's there now first, then restores the chosen snapshot: " + _r.stderr[-200:])
check(core.tm_due("Big Game") and (core.tm_record("Big Game", 0, "Big Game") or True) and not core.tm_due("Big Game"),
      "one snapshot per game per 10 minutes")
check(core.when_text("bad") == "bad" and core.when_text("2020-01-02T03:04:00Z").startswith("Jan"), "snapshot times read naturally")
# ---- Sleep guardian: fake kernel power files ----
_pw = Path(HOME) / "fake-power"; (_pw / "suspend_stats").mkdir(parents=True)
for k, v in {"success": "10", "fail": "0", "last_failed_dev": "", "last_failed_errno": "0", "last_failed_step": "",
             "last_hw_sleep": "0", "total_hw_sleep": "0"}.items():
    (_pw / "suspend_stats" / k).write_text(v + "\n")
_wk = Path(HOME) / "fake-wakeup"
_usb = Path(HOME) / "fake-sys/devices/pci0000:00/usb1/1-3"; (_usb / "power").mkdir(parents=True); (_usb / "power/wakeup").write_text("enabled")
_btn = Path(HOME) / "fake-sys/devices/LNXSYSTM:00/PNP0C0C:00"; (_btn / "power").mkdir(parents=True); (_btn / "power/wakeup").write_text("enabled")
for n, name, dev in (("wakeup0", "1-3", _usb), ("wakeup1", "PNP0C0C:00", _btn)):
    (_wk / n).mkdir(parents=True); (_wk / n / "name").write_text(name); (_wk / n / "wakeup_count").write_text("5")
    (_wk / n / "device").symlink_to(dev)
core.POWER_ROOT, core.WAKEUP_ROOT = _pw, _wk
pre = core.sleep_snapshot()
check(pre["stats"]["success"] == 10 and pre["wake"]["wakeup0"]["name"] == "1-3" and pre["wake"]["wakeup0"]["wake_file"],
      "reads suspend stats and wakeup sources")
(_wk / "wakeup0/wakeup_count").write_text("6"); (_pw / "suspend_stats/total_hw_sleep").write_text(str(int(3600 * 0.5 * 1e6)))
post = core.sleep_snapshot()
e = core.sleep_entry(pre, post, 7200, 80.0, 70.0, False)
check(e["drop"] == 10.0 and e["per_hour"] == 5.0 and e["woke_by"] == ["1-3"] and not e["failed"] and e["hw_sleep_pct"] == 25.0,
      "a sleep's cost, cause and deep-sleep share: " + str(e))
check(core.sleep_entry(pre, post, 7200, 80.0, 90.0, True)["per_hour"] is None, "charging sleeps don't count as drain")
check(core.sleep_entry(pre, dict(post, wc=pre["wc"], irq="acpi PNP0C0C"), 600, 80.0, 79.0, False)["woke_by"] == ["acpi PNP0C0C"],
      "without a counter change, the kernel's last wakeup interrupt names the cause")
check(core.sleep_snapshot(full=False).get("wake") is None and "wc" in core.sleep_snapshot(full=False), "the every-second snapshot stays light")
fl = core.sleep_failure_entry({"last_failed_dev": "xhci", "last_failed_step": "suspend"})
check(fl["failed"] and fl["slept"] == 0 and fl["failed_dev"] == "xhci", "a sleep the kernel gave up on is recorded too")
(_pw / "suspend_stats/fail").write_text("1"); (_pw / "suspend_stats/last_failed_dev").write_text("amdgpu")
fe = core.sleep_entry(post, core.sleep_snapshot(), 30, 70.0, 70.0, False)
check(fe["failed"] and fe["failed_dev"] == "amdgpu", "a failed sleep and the device behind it")
srcs = core.wakeup_sources()
f = {x["id"]: x for x in core.sleep_findings([e, e], srcs)}
check("drain" in f and "5.0%" in f["drain"]["detail"] and "deepest sleep" in f["drain"]["detail"], "flags heavy sleep drain")
short = dict(e, slept=40, per_hour=None)
f = {x["id"]: x for x in core.sleep_findings([short] * 3 + [fe], srcs)}
check(f["wakes"]["fix"] and f["wakes"]["fix"]["name"] == "1-3" and "failed" in f and "amdgpu" in f["failed"]["detail"],
      "names the device that keeps waking it, with a fix, and the failed sleep")
btn = dict(short, woke_by=["PNP0C0C:00"])
check(core.sleep_findings([btn] * 3, srcs)[0]["fix"] is None, "never offers to stop the power button (or anything not USB)")
check(core.sleep_findings([], srcs) == [], "nothing to say without sleeps")
nc = core.nowake_cmd(["/devices/pci0000:00/usb1/1-3", "/devices/LNXSYSTM:00/PNP0C0C:00", '/devices/usb1/x"y',
                      "/devices/pci0000:00/usb1"])
check(nc.count("DEVPATH") == 1 and "PNP0C0C" not in nc and "udevadm" in nc and 'SUBSYSTEM=="usb"' in nc and "usb1/power" not in nc,
      "the wake rule only ever covers USB devices, never a whole USB bus: " + nc[:200])
na = core.nowake_cmd([], allow=["/devices/pci0000:00/usb1/1-3"])
check("rm -f" in na and "echo enabled" in na and "1-3/power/wakeup" in na, "allowing a device again removes the rule and re-enables it now")
check(core._never_offer({"devpath": "/devices/pci0000:00/usb1", "wake_file": "/x"}), "a USB bus itself is never offered")
check(core.duration_text(7260) == "2 h 1 min" and core.duration_text(90) == "1 min", "sleep lengths read naturally")
core.record_sleep(e); check(core.sleep_log()[-1]["slept"] == 7200, "sleeps are logged")
# ---- first run: a fresh install sets itself up, updates change nothing ----
_cfgf = core.CONFIG_FILE
_bak = _cfgf.read_bytes() if _cfgf.exists() else None
if _cfgf.exists():
    _cfgf.unlink()
_fi = core.first_install(sys.executable)
_c = core.load_config()
check(_c["agent"]["enabled"] and _c["setup"]["done"] is False and len(_fi) == 2,
      "a brand new install turns the helper on and opens setup on first launch: " + str(_fi))
check(core.first_install(sys.executable) == [], "running the installer again (an update) changes nothing")
if _bak is not None:
    _cfgf.write_bytes(_bak)
check(core.load_config()["setup"]["done"] is True or _bak is None, "existing installs count as set up")
check("--gamemode" in core.gamemode_desktop_text(), "the Game Mode entry opens the controller layout")
_cl = core.setup_checklist({"password": False, "decky": {}})
check([k for k, _t, _d in _cl] == ["password", "decky", "steam", "agent"] and not _cl[0][2], "the setup checklist knows what's left")
_rq = core.run_quiet
_pw = {}
for _out, _want in ((core.USER + " P 01/01/2026 0 99999 7 -1", True), (core.USER + " NP 01/01/2026 0 99999 7 -1", False),
                    (core.USER + " L 01/01/2026 0 99999 7 -1", False), ("someone P", None), ("", None), ("garbage", None)):
    core.run_quiet = lambda cmd, timeout=8, o=_out: (0 if o else 1, o)
    _pw[_out] = core.sudo_password_set() is _want
core.run_quiet = _rq
check(all(_pw.values()), "password check says no only when passwd clearly says no: " + str(_pw))
check(core.DEFAULT_CONFIG["setup"]["password_known"] is False, "'I already have one' is remembered in setup")
# ---- reports: attachments, snapshot, instant upload, per-version repeats, manual reports ----
posts = []
def _fake_gh(method, path, data=None, **kw):
    posts.append((method, path, data))
    if method == "GET":
        return 200, b"[]"
    if path.endswith("/issues"):
        return 201, json.dumps({"number": 77}).encode()
    return 201, b"{}"
_real_gh = core.gh_request
core.gh_request = _fake_gh
core.save_github_token("ghp_" + "x" * 36)
for f in core.pending_reports():
    f.unlink()
core.update_config(lambda c: c["updates"].__setitem__("reporting", True))
core.update_config(lambda c: c["agent"].__setitem__("remote_pin", "482913"))
p = core.queue_report("crash", "boom2", "trace " + "x" * 30000, "fp-new", attachments=[("Full job output", "line\n" * 20000)],
                      upload=False)
rep = json.loads(p.read_text())
names = [a["name"] for a in rep["attachments"]]
check(names[0] == "Full job output" and "System snapshot" in names and any("Ally Hub log" in n for n in names),
      "reports carry the full output, a system snapshot and the log as attachments")
snap = next(a["text"] for a in rep["attachments"] if a["name"] == "System snapshot")
check("Steam account folder" in snap and "Decky" in snap and "482913" not in snap and "Config" in snap,
      "snapshot covers Steam, Decky and settings, without the PIN")
check(len(rep["body"]) < 40000 and "x" * 100 in rep["body"], "issue body keeps the end of the details and stays inside GitHub's limit")
sent, failed = core.upload_reports()
issue = [x for x in posts if x[0] == "POST" and x[1].endswith("/issues")]
comments = [x for x in posts if x[0] == "POST" and "/issues/77/comments" in x[1]]
check(sent == 1 and issue and len(comments) >= 3, f"uploads the issue, then attachments as comments ({len(comments)})")
check(all(len(c[2]["body"]) <= 65536 for c in comments), "every comment fits GitHub's size limit")
check(core.queue_report("crash", "boom2", "again", "fp-new") is None and core.LAST_QUEUE == "duplicate",
      "same problem on the same version waits a while")
sentf = core.read_json(core.REPORT_SENT, {})
core.write_json(core.REPORT_SENT, {k.replace("@" + core.VERSION, "@0.0.1"): v for k, v in sentf.items()})
check(core.queue_report("crash", "boom2", "again", "fp-new", upload=False) is not None,
      "but it's reported again right away on a new version (the fix may not have worked)")
for f in core.pending_reports():
    f.unlink()
core.update_config(lambda c: c["updates"].__setitem__("reporting", False))
check(core.queue_report("crash", "auto", "x", "fp-auto") is None, "automatic reports still respect the off switch")
posts.clear()
jl = core.job_log_path("nonsteamlaunchers"); jl.parent.mkdir(parents=True, exist_ok=True); jl.write_text("full job output here")
_us = core.upload_soon
core.upload_soon = lambda: None                   # read the queued report before the upload thread removes it
up = core.user_report("Battle.net still missing", "Launchers")
check(up is not None and json.loads(up.read_text())["kind"] == "user", "Report a problem works even with automatic reports off")
check(json.loads(up.read_text())["channel"] == "stable", "reports note the update channel")
check(any("Job output" in a["name"] for a in json.loads(up.read_text())["attachments"]), "it attaches the latest task output")
core.upload_soon = _us
core.upload_soon()
time.sleep(1.5)                                   # upload_soon runs on a thread
check(any(x[1].endswith("/issues") and x[2]["title"].startswith("[report] Battle.net") for x in posts if x[2]),
      "and it's sent at once as a [report] issue")
check(core.report_update_failure("Download failed (HTTP 0)") is None, "network hiccups during updates aren't reported")
core.gh_request = _real_gh
# ---- frame generation plugins: installed like Bazzite (latest stable GitHub release) ----
import zipfile, stat as _st
ls = core.CATALOG_BY_ID["lsfg"]; fg = core.CATALOG_BY_ID["framegen"]
check("decky-lsfg-vk/releases/latest/download/Decky.LSFG-VK.zip" in ls.install
      and "Decky-Framegen/releases/latest/download/Decky-Framegen.zip" in fg.install,
      "frame gen plugins come from the latest stable GitHub release, like Bazzite")
check(ls.category == fg.category == "Game Mode plugins" and ls.requires == ("decky",), "listed under Mods with Decky")
check(core.plugin_newer("0.14.4", "0.12.9") and not core.plugin_newer("0.12.2", "0.14.4")
      and not core.plugin_newer("0.14.4", "v0.14.4"), "the store never offers an older build as an update")
fh = Path(HOME) / "fg"; plugins = fh / "homebrew/plugins"
old = plugins / "decky-lsfg-vk-pre"; old.mkdir(parents=True)
(old / "plugin.json").write_text('{"name": "Decky LSFG-VK", "author": "x"}')
exp = plugins / "decky-lsfg-vk-experimental"; exp.mkdir()
(exp / "plugin.json").write_text('{"name": "Decky LSFG-VK Experimental"}')
other = plugins / "CSSLoader"; other.mkdir()
(other / "plugin.json").write_text('{"name": "CSS Loader"}')
zpath = fh / "Decky.LSFG-VK.zip"
with zipfile.ZipFile(zpath, "w") as z:
    z.writestr("Decky LSFG-VK/plugin.json", '{"name": "Decky LSFG-VK"}')
    z.writestr("Decky LSFG-VK/package.json", '{"version": "0.14.4"}')
fbin = fh / "bin"; fbin.mkdir()
for n, body in {"sudo": '#!/bin/sh\nexec "$@"\n', "systemctl": "#!/bin/sh\nexit 0\n",
                "curl": '#!/bin/sh\nwhile [ $# -gt 1 ]; do [ "$1" = -o ] && out=$2; shift; done\ncp ' + str(zpath) + ' "$out"\n',
                "chown": "#!/bin/sh\nexit 0\n"}.items():
    (fbin / n).write_text(body); (fbin / n).chmod(0o755)
r = subprocess.run(["bash", "-c", ls.install], env=dict(os.environ, HOME=str(fh), PATH=f"{fbin}:{os.environ['PATH']}",
                   USER="deck"), capture_output=True, text=True)
check(r.returncode == 0, "frame gen install runs: " + r.stderr[-300:])
check(not old.exists() and (plugins / "Decky LSFG-VK" / "package.json").exists(),
      "the old pre-release is replaced by the stable build, even under another folder name")
check(exp.exists() and other.exists(), "other plugins (and the experimental fork) are left alone")
(fbin / "curl").write_text("#!/bin/sh\nexit 22\n")
r = subprocess.run(["bash", "-c", ls.install], env=dict(os.environ, HOME=str(fh), PATH=f"{fbin}:{os.environ['PATH']}",
                   USER="deck"), capture_output=True, text=True)
check(r.returncode != 0 and (plugins / "Decky LSFG-VK").exists(), "a failed download keeps the installed plugin")
check(core.decky_version(ls, {"decky": {"decky lsfg-vk": {"dir": str(plugins / "Decky LSFG-VK"), "version": "0.14.4"}}})
      == "0.14.4", "the card shows the installed version")
"""

AGENT = r"""
import threading, subprocess, urllib.request, shutil
from pathlib import Path
import core
bat = Path(HOME) / "bat"; bat.mkdir()
for k, v in {"capacity": "42", "status": "Discharging", "power_now": "15000000", "energy_now": "50000000",
             "energy_full": "76000000", "energy_full_design": "80000000", "cycle_count": "12"}.items():
    (bat / k).write_text(v)
core.battery_dir = lambda: bat
led = Path(HOME) / "leds" / "ally:rgb:joystick_rings"; led.mkdir(parents=True)
for k, v in {"multi_index": "red green blue", "multi_intensity": "0 0 0", "max_brightness": "255", "brightness": "0"}.items():
    (led / k).write_text(v)
core.LED_ROOT = Path(HOME) / "leds"
apps = Path(HOME) / ".local/share/Steam/steamapps"; apps.mkdir(parents=True)
(apps / "appmanifest_1240440.acf").write_text('"AppState"\n{\n "appid" "1240440"\n "name" "Halo Infinite"\n}\n')
import agent
game = subprocess.Popen(["sleep", "30"], env=dict(os.environ, SteamGameId="1240440"))
# shelved by default: the agent must leave the rings alone for HueSync
core.update_config(lambda c: (c["agent"].update(enabled=True, battery_rings=True),
                              c.__setitem__("rgb", {"rgb": [0, 0, 255], "brightness": 200, "enums": {}})))
shelf = agent.Agent()
shelf.leds = core.find_leds(); shelf.update_lighting(core.battery_info())
check(shelf.led_reason == "handled by HueSync" and (led / "multi_intensity").read_text() == "0 0 0",
      "lighting shelved: agent doesn't touch the rings")
core.update_config(lambda c: c["lighting"].__setitem__("controller", "allyhub"))
core.update_config(lambda c: (c["agent"].update(enabled=True, battery_rings=True, remote=True,
                                                remote_pin="4321", remote_port=18911, guardian=True),
                              c.__setitem__("rgb", {"rgb": [0, 0, 255], "brightness": 200, "enums": {}})))
a = agent.Agent()
threading.Thread(target=a.run, daemon=True).start()
time.sleep(4)
check(a.game == "1240440" and a.seen.get("1240440") == "Halo Infinite", "detects running game by name")
check(a.led_reason == "battery rings", "battery rings active")
check((led / "multi_intensity").read_text().strip() == "255 214 0", "battery color for 42%")
check(core.read_health(), "health log written")
check(list((core.BACKUP_DIR / "auto").glob("*.tar.gz")), "daily settings snapshot")
core.update_config(lambda c: c["game_colors"].__setitem__("1240440", "#00ff00")); time.sleep(2)
check(a.led_reason == "game lighting" and (led / "multi_intensity").read_text() == "0 255 0", "per-game color wins")
# Quick Access panel: the agent's local socket, and the Decky plugin's backend talking to it
import socket as _so, asyncio as _aio, importlib.util as _iu, stat as _stat
check(core.CONTROL_SOCK.exists() and _stat.S_IMODE(core.CONTROL_SOCK.stat().st_mode) == 0o600,
      "the panel's socket exists and only this user can open it")
def _ask(req, raw=None):
    c = _so.socket(_so.AF_UNIX); c.settimeout(10); c.connect(str(core.CONTROL_SOCK))
    c.sendall(raw if raw is not None else json.dumps(req).encode() + b"\n")
    data = b""
    while not data.endswith(b"\n"):
        chunk = c.recv(65536)
        if not chunk:
            break
        data += chunk
    c.close()
    return json.loads(data)
st = _ask({"op": "status"})
check(st["game"] == "1240440" and st["game_name"] == "Halo Infinite" and st["battery"].startswith("42%")
      and st["lighting"] == "allyhub" and st["effects"] and st["watts"] == 15.0, "panel status: game, battery, lighting: " + str(st)[:300])
check(_ask({"op": "action", "name": "boost", "data": {"on": True}})["ok"] and core.load_config()["performance"]["boost"],
      "panel turns Game Boost on")
_ask({"op": "action", "name": "boost", "data": {"on": False}})
check(_ask({"op": "action", "name": "brightness", "data": {"value": 128}})["ok"] and core.load_config()["rgb"]["brightness"] == 128,
      "panel brightness slider")
check("error" in _ask(None, raw=b"not json\n") and _ask({"op": "status"})["game"] == "1240440",
      "a bad request gets an error and the agent keeps going")
check(not _ask({"op": "action", "name": "rm -rf"})["ok"], "unknown actions are refused")
_gs, _ag, _sent = core.game_settings, core.apply_game_settings, []
core.game_settings = lambda appid, kind="steam": {"options": "", "tool": "", "tools": [], "live": True}
core.apply_game_settings = lambda appid, opts, tool=None: (_sent.append((appid, opts, tool)), ["options"])[1]
a.read_game_flags(a.game)
check(_ask({"op": "status"})["game_flags"] == [] and _ask({"op": "status"})["game_live"], "reads the running game's switches")
r = _ask({"op": "action", "name": "game_flag", "data": {"key": "fsr4", "on": True}})
check(r["ok"] and _sent[-1] == (1240440, "PROTON_FSR4_UPGRADE=1 %command%", None) and _ask({"op": "status"})["game_flags"] == ["fsr4"],
      "panel switch sets the game's launch options through Steam: " + str(r))
check(a._steam_appid(str((123 << 32) | 0x02000000)) == 123, "non-Steam game ids map to their tile")
check(not _ask({"op": "action", "name": "game_flag", "data": {"key": "lsfg", "on": True}})["ok"],
      "frame generation can't be turned on before its plugin is installed (the game wouldn't start)")
a.qam_game["options"] = "--name=Don't %command%"
check(not _ask({"op": "action", "name": "game_flag", "data": {"key": "deck", "on": True}})["ok"]
      and not _ask({"op": "status"})["game_live"], "launch options the switches can't parse are never touched")
core.game_settings, core.apply_game_settings = _gs, _ag
check(_ask({"op": "action", "name": "backup"})["ok"], "panel can ask for a save backup")
sg = agent.Agent()
sg.update_sleep(core.battery_info())
mono0, boot0, pct0, ch0 = sg.sleep_last
sg.sleep_last = (mono0 - 1, boot0 - 4000, 80.0, False)       # as if the handheld slept for about an hour
sg.update_sleep(core.battery_info())
_sl = core.sleep_log()
check(_sl and 3900 < _sl[-1]["slept"] < 4100 and _sl[-1]["drop"] is not None and _sl[-1]["drop"] > 10,
      "the agent notices a sleep and what it cost: " + str(_sl[-1] if _sl else None))
sg.update_sleep(core.battery_info())
check(len(core.sleep_log()) == len(_sl), "normal ticks aren't sleeps")
_fb = Path(HOME) / "fakebin"; _fb.mkdir(exist_ok=True)
(_fb / "flatpak").write_text("#!/bin/sh\necho \"$@\" >> \"$HOME/flatpak.log\"\ncase \"$*\" in *find*) echo '{\"games\": {\"Halo Infinite\": {}}}';; esac\nexit 0\n")
(_fb / "flatpak").chmod(0o755)
os.environ["PATH"] = str(_fb) + os.pathsep + os.environ["PATH"]
a._ludusavi_t = 0
a.tm_snapshot(a.game)
_tms = core.read_json(core.TM_STATE, {})
check(_tms.get("Halo Infinite", {}).get("rc") == 0 and "--full-limit" in (Path(HOME) / "flatpak.log").read_text(),
      "a game starting gets its saves snapshotted: " + str(_tms))
a.tm_snapshot(a.game)
check(sum(1 for l in (Path(HOME) / "flatpak.log").read_text().splitlines() if "time-machine" in l and " backup " in l) == 1,
      "but not again right away")

_spec = _iu.spec_from_loader("qam_main", loader=None)
qam = _iu.module_from_spec(_spec)
exec(core.QAM_MAIN_PY, qam.__dict__)
check(qam.SOCK == str(core.CONTROL_SOCK), "the plugin finds the agent's socket")
st2 = _aio.run(qam.Plugin().status())
check(st2.get("game") == "1240440", "the Decky plugin's backend reads status from the agent")
check(_aio.run(qam.Plugin().action("boost", {"on": False})).get("ok"), "and sends actions")
qam.SOCK = "/nonexistent/agent.sock"
check(_aio.run(qam.Plugin().status()) == {"error": "agent"}, "agent off: the plugin says so instead of hanging")
base = "http://127.0.0.1:18911"
check(b"password" in urllib.request.urlopen(base + "/").read(), "remote shows PIN page")
try:
    urllib.request.urlopen(base + "/api/status"); check(False, "status should be locked")
except urllib.error.HTTPError as e:
    check(e.code == 403, "remote API locked without PIN")
import http.cookiejar as _cj
_jar = _cj.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(_jar))
check(b"password" in op.open(base + "/?pin=4321").read(), "a PIN in the address no longer unlocks (it lands in browser history)")
try:
    op.open(base + "/login", data=b"pin=1111"); check(False, "wrong PIN should fail")
except urllib.error.HTTPError as e:
    check(e.code == 403 and b"Wrong PIN" in e.read(), "a wrong PIN is refused")
op.open(base + "/login", data=b"pin=4321")
check([c.name for c in _jar] == ["ahs"] and all(len(c.value) > 20 and "4321" not in c.value for c in _jar),
      "the cookie is a random session, not the PIN")
_codes = []
for _pin in ["0000"] * 5 + ["4321"]:
    try:
        urllib.request.urlopen(base + "/login", data=f"pin={_pin}".encode()); _codes.append(200)
    except urllib.error.HTTPError as e:
        _codes.append(e.code)
check(_codes == [403] * 5 + [429], "five wrong PINs, then even the right one waits: " + str(_codes))
_rq = urllib.request.Request(base + "/api/status", headers={"Host": "evil.example.com"})
try:
    op.open(_rq); check(False, "foreign host should be refused")
except urllib.error.HTTPError as e:
    check(e.code == 403, "another domain pointed at the handheld gets nothing (DNS rebinding)")
check(agent.remote_host_ok("192.168.1.20:8787") and agent.remote_host_ok("steamdeck.local") and agent.remote_host_ok("[fe80::1]:8787")
      and not agent.remote_host_ok("attacker.com") and not agent.remote_host_ok(""), "remote host check")
st = json.loads(op.open(base + "/api/status").read())
check(st["game_name"] == "Halo Infinite", "remote status works after PIN")
(bat / "capacity").write_text("10"); time.sleep(2.2)
check(a.led_reason == "low battery", "low battery flash overrides")
core.update_config(lambda c: (c["agent"].update(low_battery_flash=False, battery_rings=False),
                              c["game_colors"].__setitem__("1240440", "preset:Rainbow")))
time.sleep(2)
seen = set()
for _ in range(15):
    seen.add((led / "multi_intensity").read_text()); time.sleep(0.07)
check(a.led_reason == "game lighting" and len(seen) > 3, "per-game effect animates the rings")
game.kill(); time.sleep(4)
check(a.game is None, "game exit detected")
r = json.loads(op.open(urllib.request.Request(base + "/api/preset", data=json.dumps({"name": "Synthwave"}).encode(),
               headers={"Content-Type": "application/json"})).read())
check(r["message"] == "Synthwave on", "remote preset button works")
time.sleep(2)
check(core.load_config()["lighting"]["effect"]["type"] == "wave" and a.led_reason == "your lighting", "remote preset becomes your lighting")
# the rings' USB device comes back under a new path after sleep: the agent must find it again
led2 = Path(HOME) / "leds" / "ally:rgb:joystick_rings_1"
shutil.move(str(led), str(led2))
time.sleep(3)
check(a.animator.ok, "animator recovers after the LED device reappears")
check(any(l.path == led2 for l in a.leds), "agent rescanned the LEDs")
shutil.move(str(led2), str(led))
time.sleep(3)
orig_frame = core.effect_frame
core.effect_frame = lambda *a_, **k_: 1 / 0
time.sleep(1.5)
core.effect_frame = orig_frame
time.sleep(2)
check(a.animator.is_alive() and a.animator.ok, "a crashing frame doesn't kill the lights")
page = op.open(base + "/").read().decode()
check("Aurora" in page and "&quot;Aurora&quot;" in page, "remote lists presets safely")
def boom():
    raise RuntimeError("feature exploded")
core.update_config(lambda c: c["updates"].__setitem__("reporting", True))
a.safely("test", boom)
check(any("feature exploded" in json.load(open(p))["body"] for p in core.pending_reports()), "agent errors become reports")
# after sleep the lighting is sent again even though nothing changed (HueSync re-sends after wake)
import types
sl = Path(HOME) / "sleepleds" / "x:rgb:rings"; sl.mkdir(parents=True)
for k, v in {"multi_index": "red green blue", "multi_intensity": "0 0 0", "max_brightness": "255",
             "brightness": "0"}.items():
    (sl / k).write_text(v)
core.LED_ROOT = sl.parent
an = agent.Animator(types.SimpleNamespace(cfg={"lighting": {}}, leds=core.find_leds()))
an.spec = (core.normalize_effect({"type": "static", "colors": ["#ff0000"]}), 255, {})
an.step()
(sl / "multi_intensity").write_text("1 1 1")       # the chip forgot while asleep
an.step()
check((sl / "multi_intensity").read_text() == "1 1 1", "unchanged effect isn't rewritten while awake")
an.clock_offset -= 120                              # wall clock jumped: the handheld slept
an.step()
check((sl / "multi_intensity").read_text() == "255 0 0", "lighting re-sent after waking up")
# streaming: with a commit-once chip method the agent draws every frame itself (no more "only breathing")
sent = []
_zf = core.hid_zone_frame
core.hid_zone_frame = lambda zones, b, leds=None, method=None: (sent.append((tuple(zones), method)), True)[1]
st = agent.Animator(types.SimpleNamespace(cfg={"lighting": {"encoding": "hid", "hid_method": "m6", "fps": 30}},
                                          leds=core.find_leds()))
st.spec = (core.normalize_effect(core.PRESETS["RGB Spiral"]), 255, {})
st.started_at -= 0.0
st.step(); time.sleep(0.12); st.step()
check(len(sent) == 2 and sent[0][0] != sent[1][0] and sent[0][1] == "m6", "agent streams changing spiral frames")
st.spec = (core.normalize_effect({"type": "breathe", "colors": ["#ff0000"]}), 255, {})
sent.clear(); st.step(); time.sleep(0.3); st.step()
check(len(sent) == 2 and sent[0][0] != sent[1][0], "breathe animates frame by frame instead of the chip's pulse")
core.hid_zone_frame = _zf
# ---- Game Boost in the agent ----
fk = Path(HOME) / "boostcpu" / "policy0"; fk.mkdir(parents=True)
(fk / "energy_performance_preference").write_text("balance_power")
(fk / "energy_performance_available_preferences").write_text("default performance balance_performance balance_power power")
core.CPUFREQ_ROOT = fk.parent
core.ppd_available = lambda: False
core._BACKEND_CACHE["at"] = 0.0
b = agent.Agent()
b.cfg = core.load_config(); b.cfg["performance"] = {"boost": True}
b.game = "1240440"; b.seen["1240440"] = "Halo Infinite"
b.update_boost({"status": "Charging"})
check(core.epp_current() == "performance" and b.boost_note == "performance", "game start boosts the CPU")
check(core.read_json(core.BOOST_STATE)["before"] == "balance_power", "boost is remembered on disk")
b.update_boost({"status": "Discharging"})
check(core.epp_current() == "balance_performance", "unplugging mid-game eases off a little")
b.game = None; b.update_boost({"status": "Discharging"})
check(core.epp_current() == "balance_power" and not core.BOOST_STATE.exists(), "quitting the game puts it back")
b.game = "1240440"; b.cfg["performance"] = {"boost": False}; b.update_boost({"status": "Charging"})
check(core.epp_current() == "balance_power", "no boost when Game Boost is off")
_cur = core.boost_current
calls = []
core.boost_current = lambda backend: (calls.append(1), _cur(backend))[1]
b.cfg["performance"] = {"boost": True}
for f in core.epp_files():
    f.write_text("performance")           # already at the target: nothing to do
b.update_boost({"status": "Charging"}); n = len(calls)
b.update_boost({"status": "Charging"}); b.update_boost({"status": "Charging"})
check(len(calls) == n and b.boost is None, "an already-boosted CPU isn't re-checked every 3 seconds")
core.boost_current = _cur
for f in core.epp_files():
    f.write_text("balance_power")
b.game = None; b.update_boost({"status": "Charging"}); b.game = "1240440"
b.cfg["performance"] = {"boost": True}; b.update_boost({"status": "Charging"})
c = agent.Agent(); c.recover_boost()
c.stopping = True
c.run()                                   # SIGTERM path: the loop exits instead of running forever
check(core.epp_current() == "balance_power" and not core.BOOST_STATE.exists(),
      "a boost left behind by a crash is undone when the agent starts")
b.boost = None
"""

UPDATE = r"""
import io, tarfile, shutil
from pathlib import Path
src = Path({root!r})
app = Path(HOME) / "app"; app.mkdir()
for f in ("allyhub.py", "core.py", "agent.py", "gui.py", "VERSION", "CHANGELOG.md"):
    shutil.copy2(next(p for p in (src / "app" / f, src / "docs" / f, src / f) if p.exists()), app / f)
(app / "VERSION").write_text("1.0.0")
sys.path.insert(0, str(app))
import core
check(core.APP_DIR == app and core.VERSION == "1.0.0", "running from install dir")

FOLDER = {{"CHANGELOG.md": "docs/"}}
def tarball(version, broken=False, folders=False):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for f in ("allyhub.py", "core.py", "agent.py", "gui.py", "CHANGELOG.md"):
            data = core.repo_file(src, f).read_bytes()
            if broken and f == "gui.py":
                data += b"\n def broken(:\n"
            sub = FOLDER.get(f, "app/") if folders else ""
            info = tarfile.TarInfo(f"Ravenor907-AllyHub-abc123/{{sub}}{{f}}"); info.size = len(data)
            t.addfile(info, io.BytesIO(data))
        v = version.encode(); info = tarfile.TarInfo("Ravenor907-AllyHub-abc123/VERSION"); info.size = len(v)
        t.addfile(info, io.BytesIO(v))
    return buf.getvalue()

REMOTE = {{"v": "1.1.0", "broken": False, "folders": False}}
def fake(method, path, data=None, **kw):
    if path.endswith("VERSION?ref=main"):
        return 200, REMOTE["v"].encode()
    if "/tarball/" in path:
        return 200, tarball(REMOTE["v"], REMOTE["broken"], REMOTE["folders"])
    return 404, b""
core.gh_request = fake

r = core.check_for_update()
check(r["available"] and r["remote"] == "1.1.0", "sees newer version")
ok, msg = core.install_update("1.1.0")
check(ok and (app / "VERSION").read_text() == "1.1.0", "installs update: " + msg)
check(core.previous_version() == "1.0.0", "keeps previous version")
check(core.update_state()["pending"] == "1.1.0", "new version on probation")

core.VERSION = "1.1.0"
for _ in range(core.MAX_UNHEALTHY_BOOTS):
    check(core.startup_check("gui") == "probation", "boot while on probation")
check(core.startup_check("gui") == "rolled_back", "crash loop triggers rollback")
check((app / "VERSION").read_text() == "1.0.0", "previous version restored")
check("1.1.0" in core.update_state()["bad"], "bad version remembered")
core.VERSION = "1.0.0"
check(not core.check_for_update()["available"], "bad version is skipped")

REMOTE.update(v="1.2.0", broken=True)
ok, msg = core.install_update("1.2.0")
check(not ok and "syntax error" in msg and (app / "VERSION").read_text() == "1.0.0", "rejects broken update")

REMOTE.update(v="1.2.1", broken=False)
ok, _ = core.install_update("1.2.1")
core.VERSION = "1.2.1"
check(core.startup_check("agent") == "probation", "probation after good update")
core.update_config(lambda c: c["agent"].__setitem__("enabled", True))
core.mark_healthy("agent")
check(core.on_probation() and core.on_probation("gui") and not core.on_probation("agent"),
      "the helper working doesn't end probation for the window (what let 1.4.0 slip through)")
core.mark_healthy("gui")
check(not core.on_probation(), "both parts worked: probation over")
# the 1.4.0 case: the helper is fine, the window crashes on every start
REMOTE.update(v="1.2.2", broken=False)
ok, _ = core.install_update("1.2.2")
core.VERSION = "1.2.2"
check(core.startup_check("agent") == "probation", "helper starts")
core.mark_healthy("agent")
_rs = []
_rsa = core.restart_agent_service
core.restart_agent_service = lambda: _rs.append(1)
for _ in range(core.MAX_UNHEALTHY_BOOTS):
    check(core.startup_check("gui") == "probation", "window start counted on its own")
check(core.startup_check("gui") == "rolled_back" and (app / "VERSION").read_text() == "1.2.1" and _rs,
      "the window failing to start rolls back even though the helper was fine, and the helper restarts on the old files")
core.restart_agent_service = _rsa
check(core.startup_check("agent") == "ok", "after the rollback nothing is on probation")
_st = core.update_state(); _st.update(pending=core.VERSION, boots=2); core.save_update_state(_st)
check(core.startup_check("gui") == "probation" and core.update_state()["boots"] == {{"gui": 1}},
      "a count saved by an older version doesn't break anything")
_st = core.update_state(); _st.pop("pending"); core.save_update_state(_st)
core.VERSION = "1.2.1"
_prev = core.previous_version()
ok, msg = core.rollback("manual test")
check(ok and (app / "VERSION").read_text() == _prev, "manual rollback works")
core.VERSION = "1.0.0"
REMOTE.update(v="1.3.0", broken=False, folders=True)
ok, msg = core.install_update("1.3.0")
check(ok and (app / "VERSION").read_text() == "1.3.0" and (app / "core.py").exists() and (app / "CHANGELOG.md").exists()
      and not (app / "app").exists(), "installs from the folder layout (app/, docs/) into a flat install: " + msg)
core.VERSION = "1.3.0"
REMOTE.update(v="1.3.2", folders=True)          # checked 1.3.1, but 1.3.2 landed before the download
ok, msg = core.install_update("1.3.1")
check(ok and (app / "VERSION").read_text() == "1.3.2" and core.update_state()["pending"] == "1.3.2",
      "a newer release that landed between check and download installs instead of failing: " + msg)
core.VERSION = "1.3.2"
REMOTE.update(v="1.3.0")
ok, msg = core.install_update("1.3.3")
check(not ok and "mismatch" in msg, "never installs an older download")
# update channels: stable follows main; testing follows whichever of main and testing is newer
BR = {{"main": "1.3.2", "testing": None}}
seen = []
def fake2(method, path, data=None, **kw):
    seen.append(path)
    for b in ("main", "testing"):
        if path.endswith("VERSION?ref=" + b):
            return (200, BR[b].encode()) if BR[b] else (404, b"")
        if path.endswith("/tarball/" + b):
            return (200, tarball(BR[b])) if BR[b] else (404, b"")
    return 404, b""
core.gh_request = fake2
check(core.update_channel() == "stable" and core.load_config()["updates"]["channel"] == "stable", "everyone starts on Stable")
BR["testing"] = "1.4.0"
r = core.check_for_update()
check(not r["available"] and not any("ref=testing" in x for x in seen), "Stable never looks at the testing branch")
core.update_config(lambda c: c["updates"].__setitem__("channel", "testing"))
check(core.version_label().endswith("(testing)"), "test builds are marked as such")
r = core.check_for_update()
check(r["available"] and r["remote"] == "1.4.0" and r["branch"] == "testing" and r["stable"] == "1.3.2", "Testing sees the test build")
ok, msg = core.install_update(r["remote"], r["branch"])
check(ok and (app / "VERSION").read_text() == "1.4.0" and seen[-1].endswith("/tarball/testing")
      and core.update_state()["branch"] == "testing", "installs the test build from the testing branch: " + msg)
core.VERSION = "1.4.0"
BR["main"] = "1.4.1"
r = core.check_for_update()
check(r["available"] and r["branch"] == "main", "a newer stable fix still reaches testing devices")
BR["main"], BR["testing"] = "1.3.2", None
r = core.check_for_update()
check(not r["error"] and not r["available"], "no testing branch: testing devices simply stay put")
core.update_config(lambda c: c["updates"].__setitem__("channel", "stable"))
ok, msg = core.install_update("1.3.2", "main")
check(not ok, "a normal update never goes backwards")
ok, msg = core.install_update("1.3.2", "main", allow_older=True)
check(ok and (app / "VERSION").read_text() == "1.3.2", "leaving Testing can go back to the stable version: " + msg)
check(not core.install_update("1.3.2", "../evil")[0], "only known branches are ever downloaded")
core.update_config(lambda c: c["updates"].__setitem__("channel", "nonsense"))
check(core.update_channel() == "stable", "an unknown channel falls back to Stable")
""".format(root=str(ROOT))

GUI = r"""
import gui, core
from PySide6.QtWidgets import QApplication
gui.ask = lambda *a: True
class C:
    def __init__(s, r, g, b): s.r, s.g, s.b = r, g, b
    def red(s): return s.r
    def green(s): return s.g
    def blue(s): return s.b
    def name(s): return "#%02x%02x%02x" % (s.r, s.g, s.b)
    def isValid(s): return True
    def darker(s, *a): return s
    def lighter(s, *a): return s
errors = []
def tryit(label, fn):
    try:
        fn()
    except Exception as e:
        import traceback
        errors.append(label)
        print("FAIL", label, repr(e))
        traceback.print_exc(limit=4)
hub = gui.Hub(QApplication())
tryit("refresh", hub.refresh)
for n in hub.PAGE_NAMES + ["Plugin Store", "Appearance"]:
    tryit("go " + n, lambda n=n: hub.go(n))
check(len(hub.TABS) == 5, "five top-level tabs")
check(sorted(map(id, hub.pages)) == sorted(map(id, [p for g in hub.groups for p in g.pages])), "every page lives in a tab")
hub.go("Doctor")
check(hub.tab_index() == 3 and hub.current_page() is hub.doctor, "go() lands on the right tab and section")
hub.set_tab(0, 0)
check(hub.current_page() is hub.health, "Home opens on the health report")
hub.go("Home")
check(hub.tab_index() == 0 and hub.current_page() is hub.health, "go('Home') is the health report")
check(not any(n == "Health" for _, secs in hub.TABS[1:] for n, _ in secs), "Health isn't duplicated in Tools")
core.write_json(core.DATA_DIR / "alerts.json", [{"id": "decky-missing-1", "text": "Decky is gone"}])
hub.state["password"] = False
tryit("home notices", lambda: (hub.health.refresh_notices(hub.state), hub.dismiss_alert("decky-missing-1")))
check(core.read_json(core.DATA_DIR / "alerts.json", []) == [], "alerts dismissable from Home")
hub.state["password"] = True
tryit("tabs and sections", lambda: (hub.step_page(1), hub.step_page(-1), hub.step_sub(1), hub.step_sub(-1),
                                    hub.focus_tabs(), hub.focus_page(), hub.gamepad_x()))
hub.set_tab(1, 0)
hub.gamepad._axis(5, 32767); hub.gamepad._axis(5, -32767)
check(hub.current_page() is hub.store_page, "RT moves to the next section")
hub.gamepad._axis(2, 32767); hub.gamepad._axis(2, -32767)
check(hub.current_page() is hub.mods, "LT moves back a section")
hub.gamepad._button(5, 1)
check(hub.tab_index() == 2, "RB moves to the next tab")
tryit("refresh", hub.refresh)
hub.go("Lighting")
check(hub.current_page() is hub.lighting_section and hub.lighting_section.current() is hub.huesync_page,
      "Lighting section shows HueSync by default")
hub.state["decky"] = {}
tryit("huesync page", hub.huesync_page.refresh)
hub.state["decky"] = {"huesync": {"dir": "/x/HueSync", "name": "HueSync", "version": "3.8.0"}}
hub.huesync_page.refresh()
check(hub.huesync_page.installed(), "detects HueSync when installed")
got = []
hub.on_store_action = lambda p, a: got.append((p["name"], a))
hub.store_page.plugins = [{"name": "HueSync", "versions": [{"name": "3.8.0", "hash": "h"}]}]
_old_decky = core.CATALOG_BY_ID["decky"].check
core.CATALOG_BY_ID["decky"].check = lambda s: True
tryit("install huesync", hub.huesync_page.install)
core.CATALOG_BY_ID["decky"].check = _old_decky
check(got == [("HueSync", "install")], "Install HueSync uses the Decky plugin store")
del hub.on_store_action
tryit("interface size", lambda: (hub.appearance.refresh(), hub.appearance.save_ui_size(3)))
_th = core.load_config()["theme"]
check(core.theme_size(_th, "ui_scale", gui.GAMEMODE) == 1.5 and _th["ui_scale"] == "auto"
      and core.theme_size(_th, "ui_scale", not gui.GAMEMODE) == "auto", "interface size saved for this mode only")
tryit("text size", lambda: (hub.appearance.scale.setValue(130), hub.appearance.save_scale()))
check(core.load_config()["theme"][f"scale_{core.mode_key(gui.GAMEMODE)}"] is not None, "text size saved for this mode only")
check(core.theme_size({"scale": 110}, "scale", True) == 110 and core.theme_size({"scale": 110, "scale_gamemode": 140}, "scale", True) == 140
      and core.ui_scale({"ui_scale": "auto", "ui_scale_desktop": 1.25}, False) == 1.25,
      "each mode uses its own size, older saved sizes still count")
os.environ["QT_SCREEN_SCALE_FACTORS"] = "eDP-1=1.5;"
_pr = core.panel_resolution
core.panel_resolution = lambda: (1920, 1080)
check(core.desktop_scale() == 1.5 and core.auto_ui_scale(False) == 1.0 and core.auto_ui_scale(True) == 1.5
      and core.ui_scale({"ui_scale": "auto"}, False) == 1.0,
      "Desktop Mode's own 150% scaling isn't doubled: Auto adds nothing on top of it")
os.environ["QT_SCREEN_SCALE_FACTORS"] = "1.25"
check(core.auto_ui_scale(False) == 1.25, "and only adds what's missing")
os.environ.pop("QT_SCREEN_SCALE_FACTORS")
from pathlib import Path
(Path(HOME) / ".config").mkdir(parents=True, exist_ok=True)
(Path(HOME) / ".config/kwinoutputconfig.json").write_text(json.dumps([{"name": "outputs", "data": [{"scale": 1.5}]}]))
check(core.desktop_scale() == 1.5, "reads the scale from Plasma's saved display settings too")
(Path(HOME) / ".config/kwinoutputconfig.json").unlink()
core.panel_resolution = _pr
check("never set up" in core.emudeck_uninstall_cmd() and "uninstall.sh" in core.emudeck_uninstall_cmd(),
      "EmuDeck removal works whether or not EmuDeck was ever set up")
tryit("health", lambda: (hub.health.refresh(), hub.health.set_range(12 * 3600), hub.health.set_series("w")))
check([s for s, _ in hub.health.RANGES] == [60, 3600, 12 * 3600], "history ranges are 1 minute, 1 hour, 12 hours")
H = hub.health
H.recent.clear()
_now = time.time()
for i in range(30):
    H.recent.append({"t": _now - 58 + i * 2, "pct": 80 - i % 3, "w": 12.0 + i / 10, "cpu": 60.0, "gpu": 55.0})
H.recent.append({"t": _now - 300, "pct": 1, "w": 1.0, "cpu": 1.0, "gpu": 1.0})
got = {}
H.chart.set_data = lambda pts, *a: got.update(pts=pts, span=a[-1])
tryit("1 minute view", lambda: (H.set_series("w"), H.set_range(60), H.tick(), H.sample()))
check(got["span"] == 60 and len(got["pts"]) >= 30 and all(t >= _now - 61 for t, _ in got["pts"]),
      "1-minute chart uses the 2-second readings from the last minute only")
del H.chart.set_data
hub.health.chart.points = [(1, 2), (2, 3), (400, 5)]
tryit("chart paint", lambda: hub.health.chart.paintEvent(None))
tryit("doctor", lambda: (hub.doctor.run_checks(), hub.doctor.fix_all()))
tryit("appearance", lambda: ([hub.appearance.set_preset(t) for t in core.THEMES], hub.appearance.reset_accents(),
                             hub.appearance.save_scale(), hub.appearance.save_nav(1)))
tryit("automation", lambda: ([hub.automation.set_feature(k, False) for k, _, _ in hub.automation.FEATURES],
                             hub.automation.set_dock_lights(0), hub.automation.refresh(), hub.automation.backup_now()))
tryit("connect", lambda: (hub.connect_page.refresh(), hub.connect_page.wake(), hub.connect_page.new_pin(),
                          hub.connect_page.toggle_remote(False)))
gui.QColorDialog.getColor = staticmethod(lambda *a, **k: C(10, 200, 30))
gui.ask_color = lambda *a, **k: C(10, 200, 30)
gui.ask_text = lambda *a, **k: ("Night Drive", True)
gui.ask_item = lambda *a, **k: ("Ember", True)
L = hub.lighting
tryit("lighting refresh", L.refresh)
for name, p in core.PRESETS.items():
    tryit("preset " + name, lambda p=p: (L.set_effect(p), L.apply()))
for k in core.EFFECT_TYPES:
    tryit("type " + k, lambda k=k: (L.set_type(k), L.add_color(), L.pick_color(0), L.remove_color(),
                                    L.on_speed(250), L.on_param(40), L.on_brightness(180), L.apply()))
check(core.load_config()["lighting"]["effect"]["type"] == list(core.EFFECT_TYPES)[-1], "editor saves the effect")
L.set_type("wave"); L.apply()
tryit("save custom", L.save_custom)
check("Night Drive" in core.load_config()["lighting"]["custom"], "custom effect saved")
L.custom_pick.currentText = lambda: "Night Drive"
tryit("delete custom", L.delete_custom)
check("Night Drive" not in core.load_config()["lighting"]["custom"], "custom effect deleted")
tryit("match theme", L.match_theme)
tryit("previews paint", lambda: (L.big.paintEvent(None), L._tick()))
# guided light test against a fake packed 4-zone LED
from pathlib import Path
lz = Path(HOME) / "fakeleds" / "ally:rgb:joystick_rings"; lz.mkdir(parents=True)
for k, v in {"multi_index": "rgb rgb rgb rgb", "multi_intensity": "0 0 0 0", "max_brightness": "255",
             "brightness": "0", "multi_max_intensity": "16777215 16777215 16777215 16777215"}.items():
    (lz / k).write_text(v)
core.LED_ROOT = lz.parent
core.HIDRAW_ROOT = Path(HOME) / "nohidraw"
core.update_config(lambda c: c["updates"].__setitem__("reporting", True))
gui.QTimer.singleShot = staticmethod(lambda ms, fn: fn())
answers = iter(["Blue",                            # method 1 (hex): wrong red, skip on
                "Blue",                            # method 2 (packed)
                "Red", "Green", "Blue"])           # method 3 (packed_bgr) works
L._ask_color = lambda label: next(answers)
n_before = len(core.pending_reports())
tryit("light test finds encoding", L.test_lights)
check(core.load_config()["lighting"].get("encoding") == "packed_bgr",
      "light test moves on from a wrong encoding and saves the one that works")
reps = [json.load(open(p)) for p in core.pending_reports()]
check(len(reps) > n_before and any("Light test" in r["title"] for r in reps), "light test report queued")
body = next(r["body"] for r in reps if "Light test" in r["title"])
check("expected Red" in body and "saw Blue" in body, "report lists what was expected and seen")
L._ask_color = lambda label: "Dark / off"
core.update_config(lambda c: c["lighting"].pop("encoding", None))
tryit("light test with nothing working", L.test_lights)
check("encoding" not in core.load_config()["lighting"], "no encoding saved when nothing works")
L._ask_color = lambda label: None
tryit("light test stopped", L.test_lights)
# scenario 2: the owner's Ally X: sysfs capped at 255, but a hidraw device behind the LED
import os as _os
(lz / "multi_max_intensity").write_text("255 255 255 255")
hid = Path(HOME) / "sysbus" / "0003:0B05:1B4C.0005"; (hid / "hidraw" / "hidraw7").mkdir(parents=True)
_os.symlink(hid, lz / "device")
devdir = Path(HOME) / "fakedev"; devdir.mkdir(); (devdir / "hidraw7").write_bytes(b"")
core.DEV_ROOT = devdir
check(core.sysfs_color_capped(core.find_leds()), "detects the 255 cap")
check(core.led_hidraw(core.find_leds()[0]) == devdir / "hidraw7", "finds the hidraw node behind the LED")
check(core.led_usb_ids(core.find_leds()[0]) == ("0b05", "1b4c"), "reads USB ids from the HID device")
check("1b4c" in (core.hid_permission_cmd(core.find_leds()) or ""), "permission rule targets this controller")
core.update_config(lambda c: c["lighting"].pop("encoding", None))
_rt = core.read_text   # a capped kernel reads every zone back as 255
core.read_text = lambda p, *a: "255 255 255 255" if Path(p).name == "multi_intensity" else _rt(p, *a)
sent_packets = []
_real_send = core.hid_send
sends = []
core.hid_send = lambda node, packets, feature=False, gap=0: (sends.append((list(packets), feature)), _real_send(node, packets))[1]
seen = []
answers = iter(["Red", "Mixed L=Green R=Red",   # method 1 (m6): green came out mixed
                "Red", "Green", "Blue"])        # method 2 (m7): works
L._ask_color = lambda label: (seen.append(label), next(answers))[1]
(lz / "brightness").write_text("255")
tryit("light test via HID", L.test_lights)
check(len(seen) == 5 and seen[0].startswith("Method 1 of 5") and seen[2].startswith("Method 2 of 5"),
      "capped kernel: sysfs skipped by readback, chip methods numbered and tried in turn")
light = core.load_config()["lighting"]
check(light.get("encoding") == "hid" and light.get("hid_method") == "m7", "the method that worked is saved")
first, second = sends[0][0], sends[1][0]
check(first[0][:5] == bytes([0x5A, 0xD1, 0x09, 0x01, 0x02]) and not any(p[1:15] == b"ASUS Tech.Inc." for p in first),
      "HueSync method: no handshake, RGB enable first")
check([p[2] for p in first if p[1] == 0xB3] == [1, 2, 3, 4] and all(p[4:7] == bytes([255, 0, 0]) for p in first if p[1] == 0xB3),
      "red sent to each of the four zones")
check(any(p[1] == 0xB5 for p in first) and not any(p[1] in (0xB5, 0xB4) for p in second),
      "HueSync method commits once, later colors are zone commands only")
check((lz / "brightness").read_text() == "0", "kernel lights switched off so the driver can't re-send blue")
m7 = [ps for ps, _ in sends[2:]]
check(len(m7) >= 2 and m7[0] == m7[1], "slow method sends each color twice")
body = [json.load(open(p))["body"] for p in core.pending_reports() if "Light test" in json.load(open(p))["title"]][-1]
check("Mixed L=Green R=Red" in body, "mixed left/right answers reach the report")
picks = iter(["Left and right don't match", "Green", "Red"])
_ac = L._ask_color
del L._ask_color
L._pick = lambda text, answers: next(picks)
check(L._ask_color("Method 1 of 5") == "Mixed L=Green R=Red", "mismatched sides ask for each ring")
del L._pick
check(all(len(p) == 64 for ps, _ in sends for p in ps), "every packet is 64 bytes")
sends.clear()
tryit("apply via HID", lambda: (L.set_effect(core.PRESETS["Aurora"]), L.apply()))
check(any(p[:4] == bytes([0x5A, 0xB3, 0x01, 0x01]) for ps, _ in sends for p in ps),
      "effects use the saved method (zone by zone, chip pulse mode)")
sends.clear()
core.update_config(lambda c: c["lighting"].__setitem__("hid_method", "m4"))
tryit("apply via feature reports", lambda: L.apply())
check(sends and sends[0][1] is True, "feature-report method sends feature reports")
core.hid_send = _real_send
core.read_text = _rt
# permission: one job, the test starts by itself afterwards, and no loop when the rule is already there
chip_ok = [False]          # tests run as root, so file modes can't simulate this
_hw = core.hid_writable
core.hid_writable = lambda leds: chip_ok[0]
check(not core.lighting_access_ok(core.find_leds()), "missing chip permission detected")
submitted = []
_submit = hub.runner.submit
hub.runner.submit = lambda label, cmd, key="": submitted.append((key, cmd))
hub.state["password"] = True
gui.ask = lambda *a, **k: True
tryit("test asks for permission", L.test_lights)
check([k for k, _ in submitted] == ["rgb-perms"] and L.test_after_access, "one permission job, test queued")
chip_ok[0] = True
started = []
_start = L._start_light_test
L._start_light_test = lambda: started.append(1)
tryit("permission job done", lambda: hub.on_job_finished("rgb-perms", 0, "Lighting is now allowed"))
check(started == [1], "light test starts by itself once permission is in place")
chip_ok[0] = False
submitted.clear()
tryit("old rule file present", L.allow_access)
check([k for k, _ in submitted] == ["rgb-perms"], "an existing rule file never blocks trying again")
check("chmod 0666" in submitted[0][1] and "chmod a+w" in submitted[0][1], "permission also applies right away")
n_rep = len(core.pending_reports())
tryit("permission still blocked", lambda: hub.on_job_finished("rgb-perms", 0, "ok"))
reps = [json.load(open(p)) for p in core.pending_reports()]
check(any("permission didn't take" in r["title"] for r in reps),
      "blocked permission files a report instead of a restart loop")
body = next(r["body"] for r in reps if "permission didn't take" in r["title"])
check("chip ok: False" in body and "hidraw7" in body, "report says exactly what is blocked")
hub.runner.submit = _submit
core.hid_writable = _hw
# switching between HueSync and Ally Hub
L._start_light_test = lambda: started.append(2)
tryit("use ally hub", hub.use_allyhub_lighting)
check(started[-1] == 2, "switching to Ally Hub offers the light test")
L._start_light_test = _start
check(not core.lighting_shelved() and hub.lighting_section.current() is hub.lighting, "Ally Hub drives the rings")
tryit("use huesync", hub.use_huesync_lighting)
check(core.lighting_shelved() and hub.lighting_section.current() is hub.huesync_page, "back to HueSync")
tryit("spiral editor", lambda: (L.set_type("spiral"), L.set_spiral("layout", "mirror"),
                                 L.set_spiral("direction", "ccw"), L.set_spiral("rainbow", False),
                                 L.big.paintEvent(None), L.set_spiral("engine", "chip"), L.apply()))
check(L.effect["type"] == "spiral" and L.effect["layout"] == "mirror" and L.effect["rainbow"] is False
      and L.effect["engine"] == "chip", "spiral settings editable")
tryit("spiral preset", lambda: (L.set_effect(core.PRESETS["Neon Vortex"]), L.big.paintEvent(None), L.apply()))
tryit("live status", lambda: (L.update_live(), L.live_text()))
tryit("test lights failure", lambda: L._test_failed("Ring lights accept colors but don't change", [True]))
tryit("game effect", lambda: (core.write_json(core.DATA_DIR / "seen_games.json", {"77": "Doom"}),
                              hub.automation.pick_game_effect("77"), hub.automation.refresh()))
check(core.load_config()["game_colors"]["77"] == "preset:Ember", "per-game effect saved")
tryit("system", lambda: (hub.system.refresh(), hub.system.toggle_sd(), hub.system.backup()))
tryit("updates page", lambda: (hub.updates.refresh(), hub.updates.toggle_reporting(True), hub.updates.ack_rollback()))
tryit("updates callbacks", lambda: (hub.updates._checked({"error": None, "available": False, "remote": "0"}),
                                    hub.updates._installed((False, "nope"))))
tryit("whats new", hub.show_whats_new)
tryit("profile", lambda: (core.export_profile(hub.state), hub.import_profile(core.build_profile(hub.state))))
hub.state["password"] = True
tryit("items", lambda: [hub.on_item_action(i, "install") for i in ("decky", "com.spotify.Client", "nonsteamlaunchers")])
hub.store_page.plugins = [{"name": "CSS Loader", "author": "x", "description": "d",
                           "versions": [{"name": "2.0", "hash": "abc", "created": "2024"}], "downloads": 5}]
tryit("store", lambda: (hub.store_page.rebuild(), hub.on_store_action(hub.store_page.plugins[0], "install")))
tryit("essentials", hub.install_essentials)
tryit("agent", hub.enable_agent)
tryit("job failure report", lambda: hub.on_job_finished("decky", 1, "curl: (22) The requested URL returned error: 500"))
check(any(json.load(open(p))["kind"] == "install-failure" for p in core.pending_reports()), "failed install reported")
n = len(core.pending_reports())
tryit("ignorable failure", lambda: hub.on_job_finished("emudeck", 1, "sudo: no password was provided"))
check(len(core.pending_reports()) == n, "password cancel not reported")
tryit("gamepad", lambda: (hub.gamepad.set_enabled(True), hub.gamepad.move("down"), hub.gamepad.activate(),
                          hub.gamepad.back(), hub.gamepad._button(4, 1), hub.gamepad._axis(7, -32767),
                          hub.gamepad._axis(7, 0)))
check(all(gui.item_icon(i) in gui.ICONS for i in core.CATALOG), "every catalog item has an icon")
check(all(v in gui.ICONS for v in list(gui.ITEM_ICONS.values()) + list(gui.CATEGORY_ICONS.values())),
      "every mapped icon exists")
tryit("icon badges", lambda: [gui.monogram_badge(n, "#e11d48", 48) for n in gui.ICONS] + [gui.monogram_badge("AH", "#fff")])
import re as _re
_src = open(gui.__file__).read()
_used = _re.findall(r'(?:titled_card|Tile|monogram_badge)\("([^"]+)"', _src) + \
        _re.findall(r'\("([a-z0-9-]+)", "#[0-9a-f]{6}", "', _src)
check(_used and all(u in gui.ICONS or u == "AH" for u in _used), "every badge in the UI is an icon, not an abbreviation")
tryit("updates changelog", hub.updates.refresh)
cl = core.changelog_text()
check(cl.startswith("## 1.") and "## 1.0.0" in cl, "Updates page shows the changelog, newest first")
hub.go("Performance")
check(hub.current_page() is hub.performance and hub.TABS[3][1][0] == ("Performance", "performance"),
      "Performance is the first section of Tools")
tryit("performance refresh", hub.performance.refresh)
tryit("performance boost on", lambda: hub.performance.set_boost(True))
check(core.load_config()["performance"]["boost"] is True, "Boost my games saves the setting")
tryit("performance boost off", lambda: hub.performance.set_boost(False))
tryit("every-game fsr4 on", lambda: hub.performance.set_game_env("fsr4", True))
check(core.game_env_enabled("fsr4"), "FSR 4 switch saves the setting")
tryit("every-game fsr4 off", lambda: hub.performance.set_game_env("fsr4", False))
tryit("performance jobs", lambda: [hub.on_job_finished(k, 0, "") for k in ("boost-perms", "tuneup", "tuneup-undo")])
_perf_jobs = []
_sub = hub.runner.submit
hub.runner.submit = lambda label, cmd, key="": _perf_jobs.append((key, cmd))
gui.ask = lambda *a: True
hub.state["password"] = True
tryit("performance apply", hub.performance.apply_tuneup)
tryit("performance undo", hub.performance.undo_tuneup)
check([k for k, _ in _perf_jobs] in (["tuneup", "tuneup-undo"], ["tuneup-undo"]),
      "tune-up and undo each run as one job")
check(core.TUNEUP_BEFORE.exists() or not _perf_jobs[0][0] == "tuneup", "original values saved before tuning")
hub.runner.submit = _sub
# controller scrolling: text with no button under it must still be reachable
class _Bar:
    def __init__(s, v=0, mx=2000): s.v, s.mx = v, mx
    def value(s): return s.v
    def setValue(s, v): s.v = max(0, min(s.mx, v))
class _Pt:
    def __init__(s, y): s._y = y
    def y(s): return s._y
class _W:
    def __init__(s, y=0, h=40, inside=True): s._y, s._h, s.inside = y, h, inside
    def height(s): return s._h
    def mapTo(s, _w, _p): return _Pt(s._y)
class _Content:
    def isAncestorOf(s, w): return getattr(w, "inside", False)
class _Area:
    def __init__(s, v=0): s.bar = _Bar(v); s.vp = _W(h=800); s.content = _Content()
    def verticalScrollBar(s): return s.bar
    def viewport(s): return s.vp
    def widget(s): return s.content
GN = gui.GamepadNav
a = _Area()
check(GN._too_far(a, None, gui.DOWN), "no control below: scroll instead of doing nothing")
check(not GN._too_far(a, _W(y=900), gui.DOWN), "a control just below the screen: jump to it")
check(GN._too_far(a, _W(y=2500), gui.DOWN), "a control screens away: scroll first so the text between can be read")
check(GN._too_far(_Area(v=1500), _W(y=100), gui.UP) and not GN._too_far(_Area(v=200), _W(y=100), gui.UP),
      "same going up")
nav = hub.gamepad
check(nav.scroll_by(a, 480) and a.bar.value() == 480, "scrolls the page")
a.bar.v = 2000
check(not nav.scroll_by(a, 480), "reports when the page is already at the end")
check(nav._step(a) == 480, "a step is most of a screen")
tryit("right stick scroll", lambda: (nav._axis(4, 30000), nav._stick_scroll(), nav._axis(4, 0)))
hub.go("Launchers")
check(hub.current_page() is hub.launchers, "Launchers page lives under Install")
tryit("launchers refresh", hub.launchers.refresh)
_lj = []
_sub2 = hub.runner.submit
hub.runner.submit = lambda label, cmd, key="": _lj.append((key, cmd))
hub.launchers.picked = lambda: ["Epic Games"]
tryit("launchers add", hub.launchers.add)
check(_lj and _lj[0][0] == "nonsteamlaunchers" and "Epic Games" in _lj[0][1], "Add to Steam runs one job")
tryit("launchers job done", lambda: hub.on_job_finished("nonsteamlaunchers", 0, ""))
hub.launchers.picked = lambda: ["Youtube"]
tryit("launchers uninstall", hub.launchers.uninstall)
tryit("launchers uninstall done", lambda: hub.on_job_finished("nsl-uninstall", 0, ""))
tryit("launchers find leftovers", hub.launchers.find_leftovers)
tryit("launchers show leftovers", lambda: hub.launchers._show_leftovers([{"label": "x", "path": Path(HOME) / "x", "size": 5, "warn": "w"}]))
tryit("launchers checked", lambda: hub.launchers._checked(["Battle.net"], {"res": {"missing": [], "no_shortcut": ["Battle.net"]}, "live": False}))
tryit("fix artwork", hub.launchers.fix_artwork)
_ras = gui.rasterize_svg
gui.rasterize_svg = lambda svg, w, h: b"png:" + str(w).encode()
pngs, icon = gui.make_art({"appid": 1, "name": "Netflix", "icon_png": None, "color": None, "self": False})
check(set(pngs) == {"portrait", "wide", "hero", "logo"} and icon == b"png:256",
      "draws all four pictures, and an icon tile when the program has none")
pngs, icon = gui.make_art({"appid": 2, "name": "Ally Hub", "icon_png": None, "color": None, "self": True})
check(icon == b"png:512", "Ally Hub's own tile uses Ally Hub's logo")
check(gui.art_glyph("Xbox Game Pass")[1] == "#16a34a" and gui.art_glyph("Unknown")[0], "icon-less tiles get a fitting symbol")
_t = {"appid": 1, "name": "Battle.net", "icon_png": None, "color": None, "self": False}
tryit("art planned", lambda: hub.launchers._art_planned({"tiles": 1, "ours": 0, "todo": [_t]}, False, False))
hub.launchers._art_quiet = False
tryit("art steps", lambda: [hub.launchers._art_step() for _ in range(3)])
check(not hub.launchers._art_todo, "draws the tiles one by one")
hub.launchers._art_busy = True
hub.launchers.fix_artwork(only=["X"], quiet=True)
check(hub.launchers._art_queue == [(["X"], True, False)], "a request during a run waits its turn")
hub.launchers._art_queue = []
tryit("art ready", hub.launchers._art_ready)
check(not hub.launchers._art_busy, "the button comes back after a run")
tryit("art plan error", lambda: hub.launchers._art_planned({"error": "boom"}, False, False))
for _plan in ({"tiles": 0, "ours": 0, "todo": []}, {"tiles": 2, "ours": 1, "todo": []}, {"tiles": 2, "ours": 0, "todo": []}, None):
    tryit("art nothing to do", lambda: hub.launchers._art_planned(_plan, False, False))
gui.rasterize_svg = lambda svg, w, h: b""
_q = []
_qr = core.queue_report
core.queue_report = lambda *a, **k: _q.append(a[1]) or True
hub.launchers._art_quiet = True
hub.launchers._art_todo, hub.launchers._art_made, hub.launchers._art_total = [_t], [], 1
tryit("art draw fails", lambda: [hub.launchers._art_step() for _ in range(2)])
check(_q and "couldn't draw" in _q[-1], "a system that can't draw the art files a report")
tryit("art sent", lambda: hub.launchers._art_sent([("A", {"live": True, "files": 4}), ("B", {"live": False, "files": 4}),
                                                    ("C", {"live": False, "files": 0})], False))
check(any("didn't take" in x for x in _q), "art Steam didn't take files a report")
tryit("art sent quietly", lambda: hub.launchers._art_sent([("A", {"live": True, "files": 4})], True))
core.queue_report = _qr
gui.rasterize_svg = _ras
tryit("own picture", hub.launchers.own_picture)
check(hub.launchers.btn_art.isEnabled is not None, "the art button exists")
hub.go("Storage")
check(hub.current_page() is hub.storage, "Storage lives under Tools")
tryit("storage refresh", hub.storage.refresh)
tryit("storage scan", hub.storage.scan)
_sr = {"drives": [{"label": "Internal storage", "free": 10, "total": 100}],
       "items": [{"label": "Shader cache of X", "path": Path(HOME) / "a", "size": 5, "warn": "", "group": "safe"},
                 {"label": "Windows files of X", "path": Path(HOME) / "b", "size": 7, "warn": "saves", "group": "check"}],
       "games": [{"appid": "100", "name": "Big Game", "size": 9, "shaders": 3, "prefix": 4, "total": 16,
                  "shader_paths": [Path(HOME) / "c"], "lib": "/run/media/sd", "dir": ""}]}
tryit("storage scanned", lambda: hub.storage._scanned(_sr))
check(len(hub.storage.boxes) == 2, "lists every leftover with a checkbox")
tryit("storage clean", hub.storage.clean)
tryit("storage scan failed", lambda: hub.storage._scanned({"error": "boom"}))
_ai = gui.ask_item
gui.ask_item = lambda *a, **k: ("Clear its shader cache", True)
tryit("storage game menu", lambda: hub.storage.game_menu(_sr["games"][0]))
gui.ask_item = lambda *a, **k: ("Uninstall it in Steam", True)
tryit("storage uninstall", lambda: hub.storage.game_menu(_sr["games"][0]))
gui.ask_item = _ai
tryit("storage job done", lambda: hub.on_job_finished("storage-clean", 0, ""))
hub.go("Games")
check(hub.current_page() is hub.games, "Game settings live under Tools")
tryit("games refresh", hub.games.refresh)
_gm = {"appid": 100, "name": "Big Game", "kind": "steam", "last": 1}
tryit("games listed", lambda: hub.games._listed({"games": [_gm, {"appid": 7, "name": "Tile", "kind": "shortcut", "last": 0}] * 15, "live": False}))
tryit("games show all", hub.games.expand)
tryit("games open", lambda: hub.games.open_game(_gm))
_gs = {"options": "PROTON_LOG=1 mangohud %command%", "tool": "", "tools": [("GE-Proton9-27", "GE-Proton9-27")], "live": True}
tryit("games loaded", lambda: hub.games._loaded(_gm, _gs))
check(hub.games.other == "mangohud %command%" and set(hub.games.checks) == set(core.GAME_TOGGLES), "one game's switches and its other options")
_at = gui.ask_text
gui.ask_text = lambda *a, **k: ("-dx11", True)
tryit("games edit other", hub.games.edit_other)
gui.ask_text = _at
check(hub.games.other == "-dx11", "other options can be edited")
tryit("games save", hub.games.save)
tryit("games saved", lambda: hub.games._saved(_gm, "x", "", ["options"]))
tryit("games save failed", lambda: hub.games._saved(_gm, "x", "", []))
_ai = gui.ask_item
for _c in ("Try a different Proton", "Turn on the troubleshooting log", "Send the log from the last launch",
           "Reset its Windows files (the old ones are kept)", "Check the game's files in Steam"):
    gui.ask_item = lambda *a, _c=_c, **k: (_c if "Game won't" in a[1] else "GE-Proton9-27", True)
    tryit("games rescue " + _c, hub.games.rescue)
gui.ask_item = _ai
tryit("games back", hub.games.back)
tryit("games load failed", lambda: (hub.games.open_game(_gm), hub.games._loaded(_gm, {"error": "x"})))
tryit("game reset done", lambda: hub.on_job_finished("game-reset", 0, ""))
_ss, _later = gui.QTimer.singleShot, []
gui.QTimer.singleShot = staticmethod(lambda ms, fn: _later.append(fn))
hub._sheet = object()
gui.msg_info(None, "t", "x")
hub._sheet = None
gui.QTimer.singleShot = _ss
check(len(_later) == 1, "a message while a pop-up is open waits instead of opening a window")
tryit("deferred message shows later", _later[0])
tryit("games loaded (unparseable)", lambda: (setattr(hub.games, "game", _gm), hub.games._loaded(_gm, dict(_gs, options="--name=Don't %command%"))))
check(not hub.games.parseable and hub.games.new_options() == "--name=Don't %command%", "unparseable options are saved back untouched")
tryit("games loaded again", lambda: (setattr(hub.games, "game", _gm), hub.games._loaded(_gm, _gs)))
for _k, _cb in hub.games.checks.items():           # the mock's checkboxes don't remember their state
    _cb.isChecked = (lambda _k=_k: _k in hub.games.flags0)
check(hub.games.new_options() == _gs["options"], "unchanged settings save the exact original text")
hub.games.checks["deck"].isChecked = lambda: True
check(hub.games.new_options() == "SteamDeck=1 PROTON_LOG=1 mangohud %command%", "one switch changes only its own token")
tryit("panel card", hub.games.qam_card)
_lj.clear()
hub.runner.submit = lambda label, cmd, key="": _lj.append((key, cmd))
hub.state["decky"] = {"x": {"dir": "/x", "name": "x"}}
_np = hub.needs_password
hub.needs_password = lambda: False
_dk = gui.CATALOG_BY_ID["decky"].check
gui.CATALOG_BY_ID["decky"].check = lambda st: True
tryit("panel install", hub.games.qam_install)
check(_lj and _lj[-1][0] == "qam-install" and "plugin_loader" in _lj[-1][1], "Add to Quick Access runs one job")
gui.CATALOG_BY_ID["decky"].check = _dk
hub.needs_password = _np
tryit("panel remove", hub.games.qam_remove)
tryit("panel done", lambda: hub.on_job_finished("qam-install", 0, ""))
hub.runner.submit = _sub2
hub.go("Updates")
tryit("channel to testing", lambda: (hub.updates.channel.setCurrentIndex(1), hub.updates.change_channel()))
_cd = hub.updates.channel.currentData
hub.updates.channel.currentData = lambda: "testing"
tryit("channel change", hub.updates.change_channel)
check(core.update_channel() == "testing", "the Updates page switches to test builds")
tryit("channel checked: back to stable", lambda: hub.updates._channel_checked("stable", {"stable": "0.0.1", "available": False}))
tryit("channel checked: update", lambda: hub.updates._channel_checked("testing", {"available": True, "remote": "9.0.0", "branch": "testing"}))
tryit("channel checked: offline", lambda: hub.updates._channel_checked("testing", {"error": "x"}))
hub.updates.channel.currentData = _cd
core.update_config(lambda c: c["updates"].__setitem__("channel", "stable"))
# plugins: off/on from cards, the store list and safe mode
_sub3 = hub.runner.submit
_lj.clear()
hub.runner.submit = lambda label, cmd, key="": _lj.append((key, cmd))
_np2 = hub.needs_password
hub.needs_password = lambda: False
hub.state["decky"] = {"allycenter": {"dir": "/h/homebrew/plugins/AllyCenter", "name": "Ally Center", "version": "1"},
                      "huesync": {"dir": "/h/homebrew/plugins/HueSync", "name": "HueSync", "version": "2"}}
hub.state["decky_off"] = ["HueSync"]
tryit("plugin card off", lambda: hub.on_item_action("allycenter", "disable"))
check(_lj and _lj[-1][0] == "allycenter" and "Ally Center" in _lj[-1][1] and " off " in _lj[-1][1], "a plugin card turns it off")
tryit("plugin card on", lambda: hub.on_item_action("allycenter", "enable"))
check(" on " in _lj[-1][1], "and back on")
tryit("your plugins list", hub.store_page.show_mine)
core.DECKY_SAFE_MODE.unlink(missing_ok=True)
tryit("safe mode off", hub.store_page.safe_mode)
check(core.read_json(core.DECKY_SAFE_MODE) == ["Ally Center"] and _lj[-1][0] == "decky-safe",
      "safe mode turns off every plugin that was on, and remembers which")
tryit("safe mode back on", hub.store_page.safe_mode)
check(" on " in _lj[-1][1] and "Ally Center" in _lj[-1][1], "and turns exactly those back on")
_gs2 = core.gather_state
core.gather_state = lambda: {"flatpaks": [], "decky": hub.state["decky"], "decky_off": []}
tryit("safe mode job done", lambda: hub.on_job_finished("decky-safe", 0, ""))
core.gather_state = _gs2
check(not core.DECKY_SAFE_MODE.exists(), "safe mode clears once they're back on")
tryit("remove from your plugins", lambda: hub.remove_decky(hub.state["decky"]["huesync"]))
check(_lj[-1][0] == "decky-mine:HueSync" and "HueSync" in _lj[-1][1], "any installed plugin can be removed from the list")
tryit("store row toggle", lambda: hub.on_store_action({"name": "HueSync"}, "enable"))
tryit("update cards with an off plugin", hub.update_cards)
hub.needs_password = _np2
# launchers: hide from Steam, quick restore
hub.launchers.picked = lambda: ["Youtube"]
tryit("launchers hide", hub.launchers.hide)
check(hub.launchers.restorable(["Youtube"]) and not hub.launchers.restorable(["Battle.net"]) and not hub.launchers.restorable([]),
      "web launchers and installed stores can come back without reinstalling")
tryit("launchers quick restore", hub.launchers.add)
hub.runner.submit = _sub3
hub.go("Saves")
check(hub.current_page() is hub.saves, "Saves live under Tools")
tryit("saves refresh", hub.saves.refresh)
tryit("saves on", lambda: hub.saves.set_on(True))
check(core.load_config()["saves"]["time_machine"], "the time machine can be turned on")
tryit("saves keep", lambda: hub.saves.set_keep(2))
check(core.load_config()["saves"]["keep"] == 10, "and told how many to keep")
_snaps = {"Big Game": [{"name": "b2", "when": "2026-10-03T10:00:00Z"}, {"name": "b1", "when": "2026-10-01T10:00:00Z"}]}
tryit("saves loaded", lambda: hub.saves._loaded(_snaps))
tryit("saves empty", lambda: hub.saves._loaded({}))
hub.saves.snaps = _snaps
_ai3, _sub4 = gui.ask_item, hub.runner.submit
_tm = []
hub.runner.submit = lambda label, cmd, key="": _tm.append((key, cmd))
gui.ask_item = lambda *a, **k: (core.when_text("2026-10-01T10:00:00Z"), True)
tryit("saves restore", lambda: hub.saves.pick("Big Game"))
check(_tm and _tm[-1][0] == "tm-restore" and "b1" in _tm[-1][1], "picking a snapshot restores that one")
hub.saves.undo = {"Big Game": [{"name": "u1", "when": "2026-10-04T10:00:00Z"}]}
gui.ask_item = lambda *a, **k: (a[3][0], True)
tryit("saves undo", lambda: hub.saves.pick("Big Game"))
check("u1" in _tm[-1][1] and str(core.TM_BEFORE_RESTORE) in _tm[-1][1], "the last restore can be undone from the same list")
tryit("saves loaded (both lists)", lambda: hub.saves._loaded({"tm": _snaps, "undo": {}}))
gui.ask_item, hub.runner.submit = _ai3, _sub4
tryit("saves restore done", lambda: hub.on_job_finished("tm-restore", 0, ""))
hub.go("Sleep")
check(hub.current_page() is hub.sleep, "Sleep lives under Tools")
tryit("sleep refresh empty", hub.sleep.refresh)
_sle = {"end": 1, "slept": 40, "pct_before": 80, "pct_after": 79, "drop": 1, "charging": False, "per_hour": None,
        "woke_by": ["1-3"], "failed": False, "failed_dev": "", "failed_step": "", "hw_sleep_pct": None}
core.write_json(core.SLEEP_LOG, [_sle] * 3)
_ws = core.wakeup_sources
core.wakeup_sources = lambda: {"w0": {"name": "1-3", "count": 1, "devpath": "/devices/pci0000:00/usb1/1-3", "wake_file": "/x"}}
tryit("sleep refresh with findings", hub.sleep.refresh)
_np5, _sub5 = hub.needs_password, hub.runner.submit
_sj = []
hub.needs_password = lambda: False
hub.runner.submit = lambda label, cmd, key="": _sj.append((key, cmd))
tryit("sleep stop wake", lambda: hub.sleep.stop_wake({"kind": "nowake", "devpath": "/devices/pci0000:00/usb1/1-3", "name": "1-3"}))
check(_sj and _sj[-1][0] == "sleep-nowake" and core.load_config()["sleep"]["no_wake"] == [],
      "stopping a device only changes the saved list once the job worked")
tryit("sleep nowake done", lambda: hub.sleep.job_done(True))
check(core.load_config()["sleep"]["no_wake"] == ["/devices/pci0000:00/usb1/1-3"], "a device can be stopped from waking the handheld")
tryit("sleep allow wake", lambda: hub.sleep.allow_wake("/devices/pci0000:00/usb1/1-3"))
tryit("sleep allow failed", lambda: hub.sleep.job_done(False))
check(core.load_config()["sleep"]["no_wake"] == ["/devices/pci0000:00/usb1/1-3"], "a failed job leaves the list as it was")
tryit("sleep allow wake again", lambda: (hub.sleep.allow_wake("/devices/pci0000:00/usb1/1-3"), hub.sleep.job_done(True)))
check(core.load_config()["sleep"]["no_wake"] == [] and "echo enabled" in _sj[-1][1], "and allowed again, right away")
hub.needs_password, hub.runner.submit = _np5, _sub5
core.wakeup_sources = _ws
tryit("sleep send details", hub.sleep.send_details)
tryit("sleep job done", lambda: hub.on_job_finished("sleep-nowake", 0, ""))
hub.go("Setup")
check(hub.current_page() is hub.setup, "Setup lives under Home")
tryit("setup refresh", hub.setup.refresh)
_steps = hub.setup.steps()
check(_steps[0] == "welcome" and _steps[-1] == "done" and "reports" not in _steps, "the walkthrough skips reports without a key")
for _ in range(len(_steps) - 1):
    tryit("setup step " + hub.setup.steps()[hub.setup.step], hub.setup.next)
check(hub.setup.steps()[hub.setup.step] == "done", "every step can be walked through")
tryit("setup back", hub.setup.back)
# the owner (1.3.2): setup kept opening passwd after the password was set (a stale "no password")
_sps, _sp, _ai2 = core.sudo_password_set, hub.set_password, gui.ask_item
_opened = []
hub.set_password = lambda *a: _opened.append(1)
hub._pw_term = None
hub.state["password"] = False
core.sudo_password_set = lambda: True
check(hub.needs_password() is False and hub.state["password"] is True and not _opened,
      "a password set since the last look is found, no terminal")
hub.state["password"] = False
tryit("job finished re-checks the password", lambda: hub.on_job_finished("sleep-nowake", 0, ""))
check(hub.state["password"] is True, "a finished job doesn't carry an old 'no password'")
core.sudo_password_set = lambda: False
gui.ask_item = lambda *a, **k: ("Create a password", True)
hub.state["password"] = False
check(hub.needs_password() is True and len(_opened) == 1, "really no password: offers to create one")
gui.ask_item = lambda *a, **k: ("", False)
check(hub.needs_password() is True and len(_opened) == 1, "cancel doesn't open a terminal")
gui.ask_item = lambda *a, **k: ("I already have one", True)
check(hub.needs_password() is False and core.load_config()["setup"]["password_known"], "'I already have one' continues")
check(hub.refresh_password() is None and hub.needs_password() is False and len(_opened) == 1,
      "and it sticks, so passwd never opens in a loop")
core.update_config(lambda c: c["setup"].__setitem__("password_known", False))
hub.state["password"] = False
hub.setup.step = hub.setup.steps().index("password"); hub.setup.refresh()
tryit("setup: I already have one", hub.setup.already_have_password)
check(hub.setup.steps()[hub.setup.step] == "gamemode" and hub.state["password"] is None,
      "the password step moves on with 'I already have one'")
core.update_config(lambda c: c["setup"].__setitem__("password_known", False))
core.sudo_password_set = lambda: True
hub.state["password"] = False
tryit("password window closed", hub.password_window_closed)
check(hub.state["password"] is True and hub._pw_term is None, "closing the password window looks again")
hub._pw_term = os.getpid()
check(hub.password_window_open(), "a running password window is noticed")
hub._pw_term = 2 ** 22 + 12345
tryit("password window gone", hub._watch_password_window)
check(hub._pw_term is None, "the watcher notices the password window closed")
tryit("set password window", _sp)
hub._pw_term = None
core.sudo_password_set, hub.set_password, gui.ask_item = _sps, _sp, _ai2
_np6, _sub6, _ia = hub.needs_password, hub.runner.submit, hub.on_item_action
_acts = []
hub.needs_password = lambda: False
hub.on_item_action = lambda iid, action: _acts.append((iid, action))
hub.setup.step = hub.setup.steps().index("essentials"); hub.setup.refresh()
for _k, (_cb, _have) in hub.setup.essentials.items():
    _cb.isChecked = lambda: True
hub.setup.essentials = {k: (cb, False) for k, (cb, _h) in hub.setup.essentials.items()}
tryit("setup install essentials", hub.setup.install_essentials)
check(("decky", "install") in _acts and (core.LUDUSAVI_ID, "install") in _acts and hub.qam_after_decky,
      "picked essentials install, the Quick Access panel right after Decky")
hub.needs_password, hub.on_item_action = _np6, _ia
tryit("setup finish", hub.setup.finish)
check(core.load_config()["setup"]["done"] is True, "finishing marks setup done")
tryit("home checklist", lambda: hub.health.refresh_notices({"password": False, "decky": {}}))
tryit("home checklist hide", hub.health.hide_setup)
check(core.load_config()["setup"]["checklist_hidden"], "the Home reminder can be hidden")
hub.qam_after_decky = False
tryit("NSL card opens the page", lambda: hub.on_item_action("nonsteamlaunchers", "install"))
check(hub.current_page() is hub.launchers, "the catalog card opens the themed page, not the script's windows")
# header/footer on the sides
check(core.load_config()["theme"]["bars"] == "top", "header and footer start at the top and bottom")
tryit("bars to sides", lambda: hub.appearance.save_bars(1))
check(core.load_config()["theme"]["bars"] == "sides" and hub.bars == "sides", "side layout is saved and applied live")
hub.gamepad.enabled = True
tryit("pad in side mode", lambda: hub.gamepad.move(gui.RIGHT))
tryit("bars back to top", lambda: hub.appearance.save_bars(0))
check(hub.bars == "top" and core.load_config()["theme"]["bars"] == "top", "and back")
_src = open(gui.__file__).read()
check("QWidget().setLayout" not in _src, "never hands a layout to a throwaway widget (it takes the widgets with it)")
tryit("switch layouts repeatedly", lambda: [hub.arrange_bars(m) for m in ("sides", "top", "sides", "top")])
tryit("side icons", lambda: (hub.arrange_bars("sides"), hub.apply_theme(), hub.update_top_status(), hub.arrange_bars("top")))
check(all(k in gui.ICONS for k in gui.TAB_ICONS.values()) and all(i in gui.ICONS for _, i, _, _ in hub.FOOT_BUTTONS),
      "every side-bar icon exists")
check('#topBar[side="true"]' in gui.build_qss(core.theme_palette({"preset": "ROG Crimson"}), 100), "side bars have their own borders")
_vk = gui.key_hints(gui.PAD_KEYS, vertical=True)
tryit("report a problem", hub.report_problem)
# baseline: controller everywhere, no extra windows, footer off by default, one instance
import re as _re2
_src = open(gui.__file__).read()
check(not _re2.search(r"QMessageBox\.(information|warning|critical|question)\(", _src)
      and "QInputDialog.getText(" not in _src and "QInputDialog.getItem(" not in _src,
      "no stand-alone message, text or list windows: everything opens inside Ally Hub")
_exec = [m.start() for m in _re2.finditer(r"\.exec\(\)", _src)]
_rd = _src.index("def run_dialog"); _rd_end = _src.index("def _focus_first")
check(all(_rd < i < _rd_end for i in _exec[:-1]) and _src.count("app.exec()") == 1,
      "dialogs only run through run_dialog (the in-window panel)")
check(core.load_config()["theme"]["footer"] is False, "the bottom bar is off by default")
tryit("footer on/off", lambda: (hub.appearance.save_footer(True), hub.appearance.save_footer(False)))
tryit("in-window ask", lambda: gui.ask(None, "Sure?"))
tryit("in-window info", lambda: gui.msg_info(None, "t", "x"))
tryit("controller in a drop-down", lambda: (hub.gamepad.move(gui.DOWN), hub.gamepad.activate(), hub.gamepad.back()))
check(hasattr(gui, "single_instance") and "QLocalServer" in _src, "only one Ally Hub runs at a time")
check("QFileDialog.DontUseNativeDialog" in _src and "def pick_color" in _src, "file and color pickers work with the controller")
check("Anthropic's AI" in open(gui.__file__).read() and "Anthropic's AI" in open(os.path.join(os.path.dirname(gui.__file__), "..", "README.md")).read(),
      "the app and the README disclose that Claude builds Ally Hub")
tryit("qss", lambda: [gui.build_qss(core.theme_palette({"preset": t}), 120) for t in core.THEMES])
check(not errors, "no errors in GUI actions")
"""


def main() -> int:
    results = [
        run_section("compile", COMPILE),
        run_section("core", CORE),
        run_section("agent", AGENT),
        run_section("update + rollback", UPDATE),
        run_section("gui (mock Qt)", GUI, mock_qt=True),
    ]
    print(f"\n{sum(results)}/{len(results)} sections passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
