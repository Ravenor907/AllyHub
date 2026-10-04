#!/usr/bin/env python3
"""
Ally Hub: a mod, theme and automation center for SteamOS on the ROG Xbox Ally X.

  allyhub              open the app
  allyhub --gamemode   fullscreen with controller navigation (used from Steam)
  allyhub --fullscreen fullscreen in Desktop Mode
  allyhub --agent      run the background agent (started by systemd)
  allyhub --apply-rgb  re-apply your saved lighting once
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def run():
    if "--agent" in sys.argv:
        import agent
        return agent.main()
    if "--apply-rgb" in sys.argv:
        import core
        cfg = core.load_config()
        rgb = cfg.get("rgb")
        if not rgb or core.lighting_shelved(cfg):
            return 0
        light = cfg.get("lighting") or {}
        if light.get("encoding") == "hid":
            effect = core.base_effect(cfg) or core.normalize_effect(
                {"type": "static", "colors": [core.rgb_to_hex(rgb["rgb"])]})
            return 0 if core.hid_apply_effect(effect, int(rgb["brightness"]), None, light.get("hid_method")) else 1
        ok = core.apply_lighting(tuple(rgb["rgb"]), int(rgb["brightness"]), rgb.get("enums", {}))
        return 0 if ok else 1
    import gui
    return gui.main()


if __name__ == "__main__":
    sys.exit(run())
