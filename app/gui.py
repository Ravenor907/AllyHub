"""
Ally Hub GUI (PySide6).
"""

import collections
import json
import os
import secrets
import shlex
import shutil
import struct
import sys
import time
import traceback
from pathlib import Path
from typing import Optional

import core
from core import (APP_NAME, CATALOG, CATALOG_BY_ID, HOME, USER, VERSION, Item, load_config,
                  update_config)

from PySide6.QtCore import (QBuffer, QByteArray, QEvent, QIODevice, QObject, QPoint, QPointF, QProcess, QProcessEnvironment, QRectF, QSize,
                            QSocketNotifier, Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QIcon, QImage, QImageReader, QKeyEvent, QPainter,
                           QPainterPath, QPen, QPixmap, QTextCursor)
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QAbstractScrollArea, QApplication, QCheckBox, QColorDialog, QComboBox,
    QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel, QLayout, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
    QScrollArea, QScroller, QSizePolicy, QSlider, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

GAMEMODE = "--gamemode" in sys.argv or core.in_game_mode()


# ==========================================================================
# Theme engine
# ==========================================================================

def build_qss(p: dict, scale: int) -> str:
    def fs(px):
        return max(9, round(px * scale / 100))
    a, a2, on = p["accent"], p["accent2"], p["on_accent"]
    h1, h2, h3 = p["hero"]
    hero_sub = p["muted"] if p.get("light") else "#d9d2ee"
    return f"""
* {{ font-family: "Noto Sans", "Inter", "Segoe UI", sans-serif; color: {p['text']}; }}
QMainWindow, #root, QDialog, QMessageBox {{ background: {p['bg']}; }}
#dimmer {{ background: rgba(0, 0, 0, 160); }}
#sheet {{ background: {p['surface']}; border: 2px solid {a2}; border-radius: 18px; }}
#sidebar {{ background: {p['side']}; border-right: 1px solid {p['border']}; }}
#brand {{ font-size: {fs(22)}px; font-weight: 700; padding: 6px 4px; }}
#brandSub {{ color: {p['muted']}; font-size: {fs(12)}px; padding: 0 4px 10px 4px; }}
QListWidget#nav {{ background: transparent; border: none; outline: none; font-size: {fs(15)}px; }}
QListWidget#nav::item {{ padding: {fs(9)}px 14px; margin: 1px 0; border-radius: 12px; color: {p['muted']}; }}
QListWidget#nav::item:hover {{ background: {p['surface2']}; color: {p['text']}; }}
QListWidget#nav::item:selected {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {a}, stop:1 {a2});
    color: {on}; font-weight: 700;
}}
QListWidget#nav:focus {{ border: 2px solid {a2}; border-radius: 14px; }}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
#pageTitle {{ font-size: {fs(30)}px; font-weight: 700; }}
#pageSub {{ color: {p['muted']}; font-size: {fs(15)}px; }}
#section {{ color: {p['muted']}; font-size: {fs(13)}px; font-weight: 700; letter-spacing: 1px; padding-top: 10px; }}
#card {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 18px; }}
#hero {{
    border-radius: 22px; border: 1px solid {p['border']};
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {h1}, stop:0.55 {h2}, stop:1 {h3});
}}
#heroTitle {{ font-size: {fs(34)}px; font-weight: 700; }}
#heroSub {{ color: {hero_sub}; font-size: {fs(16)}px; }}
#cardTitle {{ font-size: {fs(18)}px; font-weight: 700; }}
#cardMeta {{ color: {p['muted']}; font-size: {fs(12)}px; }}
#cardDesc {{ color: {p['muted']}; font-size: {fs(14)}px; }}
#cardWarn {{ color: #d97706; font-size: {fs(13)}px; }}
#statLabel {{ color: {p['muted']}; font-size: {fs(13)}px; }}
#statValue {{ font-size: {fs(18)}px; font-weight: 700; }}
#bigValue {{ font-size: {fs(26)}px; font-weight: 700; }}
#pill {{ border-radius: 10px; padding: 4px 12px; font-size: {fs(12)}px; font-weight: 700; }}
#pill[state="on"] {{ background: #0f3d26; color: #4ade80; }}
#pill[state="off"] {{ background: {p['surface2']}; color: {p['muted']}; }}
#pill[state="busy"] {{ background: #3a2a0c; color: #fbbf24; }}
#pill[state="update"] {{ background: #1e2a4d; color: #93c5fd; }}
#pill[state="tool"] {{ background: {p['surface2']}; color: {a2}; }}
#pill[state="warn"] {{ background: #3a2a0c; color: #fbbf24; }}
#pill[state="fail"] {{ background: #3b1218; color: #fb7185; }}
QPushButton {{
    background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 12px;
    padding: {fs(9)}px {fs(18)}px; font-size: {fs(15)}px; font-weight: 500; min-height: {fs(22)}px;
}}
QPushButton:hover {{ border: 1px solid {a2}; }}
QPushButton:focus {{ border: 3px solid {a2}; }}
QPushButton:disabled {{ color: {p['muted']}; background: {p['surface']}; }}
QPushButton#primary {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {a}, stop:1 {a2});
    border: none; color: {on};
}}
QPushButton#primary:focus {{ border: 3px solid {p['text']}; }}
QPushButton#primary:disabled {{ background: {p['surface2']}; color: {p['muted']}; }}
QPushButton#danger {{ background: transparent; border: 1px solid #7f2a3a; color: #fb7185; }}
QPushButton#danger:focus {{ border: 3px solid #fb7185; }}
QPushButton#chip {{ padding: 7px 15px; font-size: {fs(14)}px; border-radius: 17px; }}
QPushButton#chip:checked {{ background: {a2}; border: none; color: {on}; }}
QPushButton#swatch {{ border-radius: 22px; min-width: 44px; max-width: 44px; min-height: 44px; max-height: 44px; padding: 0; }}
QPushButton#themeCard {{ text-align: left; padding: 0; border-radius: 16px; background: transparent; border: 2px solid {p['border']}; }}
QPushButton#themeCard:checked {{ border: 3px solid {a}; }}
QPushButton#themeCard:focus {{ border: 3px solid {a2}; }}
QLineEdit, QSpinBox {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 12px; padding: 10px 14px; font-size: {fs(15)}px; }}
QLineEdit:focus, QSpinBox:focus {{ border: 2px solid {a2}; }}
QCheckBox {{ font-size: {fs(15)}px; spacing: 12px; padding: 4px; }}
QCheckBox:focus {{ border: 2px solid {a2}; border-radius: 10px; }}
QCheckBox::indicator {{ width: 44px; height: 24px; border-radius: 12px; background: {p['surface2']}; border: 1px solid {p['border']}; }}
QCheckBox::indicator:checked {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {a}, stop:1 {a2}); border: none; }}
#banner {{ background: #2b1d07; border: 1px solid #6b4a0e; border-radius: 14px; }}
#toastPop {{ background: {p['surface2']}; color: {p['text']}; border: 1px solid {p['border']}; border-radius: 16px; padding: 12px 22px; font-size: {fs(15)}px; }}
#bannerText {{ color: #fcd34d; font-size: {fs(15)}px; }}
#statusBar {{ background: {p['side']}; border-top: 1px solid {p['border']}; }}
#statusBar[side="true"] {{ border-top: none; border-left: 1px solid {p['border']}; }}
#statusText {{ color: {p['muted']}; font-size: {fs(14)}px; }}
QProgressBar {{ background: {p['surface2']}; border: none; border-radius: 4px; max-height: 8px; }}
QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {a}, stop:1 {a2}); border-radius: 4px; }}
QPlainTextEdit#log {{
    background: {p['side']}; border: 1px solid {p['border']}; border-radius: 14px;
    font-family: "Noto Sans Mono", "DejaVu Sans Mono", monospace; font-size: {fs(13)}px; padding: 10px;
}}
QSlider::groove:horizontal {{ height: 8px; background: {p['surface2']}; border-radius: 4px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {a}, stop:1 {a2}); border-radius: 4px; }}
QSlider::handle:horizontal {{ background: {p['text']}; width: 24px; height: 24px; margin: -8px 0; border-radius: 12px; }}
QSlider:focus {{ border: 2px solid {a2}; border-radius: 8px; }}
QComboBox {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 10px; padding: 8px 14px; font-size: {fs(15)}px; min-width: 130px; }}
QComboBox:focus {{ border: 2px solid {a2}; }}
QComboBox QAbstractItemView {{ background: {p['surface']}; selection-background-color: {a2}; font-size: {fs(15)}px; }}
QScrollBar:vertical {{ background: {p['surface']}; width: {max(24, fs(26))}px; margin: 4px 2px; border-radius: {max(12, fs(13))}px; }}
QScrollBar::handle:vertical {{ background: {p['muted']}; border-radius: {max(10, fs(11))}px; min-height: 72px; margin: 3px; }}
QScrollBar::handle:vertical:hover, QScrollBar::handle:vertical:pressed {{ background: {a2}; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
#thumb {{ background: {p['side']}; border-radius: 12px; }}
#topBar {{ background: {p['side']}; border-bottom: 1px solid {p['border']}; }}
#topBar[side="true"] {{ border-bottom: none; border-right: 1px solid {p['border']}; }}
#brandSmall {{ font-size: {fs(17)}px; font-weight: 700; }}
#topStatus {{ color: {p['muted']}; font-size: {fs(14)}px; }}
#hint {{ color: {p['muted']}; border: 1px solid {p['border']}; border-radius: 6px; padding: 1px 7px; font-size: {fs(12)}px; font-weight: 700; }}
QPushButton#tab {{ background: transparent; border: 2px solid transparent; border-radius: 18px;
    padding: {fs(7)}px {fs(20)}px; font-size: {fs(16)}px; color: {p['muted']}; }}
QPushButton#tab:hover {{ color: {p['text']}; }}
QPushButton#tab:checked {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {a}, stop:1 {a2});
    color: {on}; font-weight: 700; }}
QPushButton#tab:focus {{ border: 2px solid {p['text']}; }}
#chipBar {{ background: transparent; }}
QPushButton#presetCard {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 16px; padding: 0; }}
QPushButton#presetCard:hover {{ border: 1px solid {a2}; }}
QPushButton#presetCard:checked {{ border: 2px solid {a}; background: {p['surface2']}; }}
QPushButton#presetCard:focus {{ border: 3px solid {a2}; }}
#presetName {{ font-size: {fs(14)}px; font-weight: 700; }}
#statPill {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 14px;
    padding: 6px 14px; font-size: {fs(15)}px; }}
#statPill[state="ok"] {{ color: #4ade80; border: 1px solid #1f6b3e; }}
#statPill[state="warn"] {{ color: #fbbf24; border: 1px solid #7a5a14; }}
#key {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-bottom: 2px solid {p['border']};
    border-radius: 6px; padding: 1px 7px; font-size: {fs(12)}px; font-weight: 700; color: {p['text']}; }}
#keyText {{ color: {p['muted']}; font-size: {fs(13)}px; }}
#footInfo {{ color: {p['muted']}; font-size: {fs(13)}px; }}
QMessageBox QLabel {{ font-size: {fs(15)}px; }}
"""


# ==========================================================================
# Job runner
# ==========================================================================

import re  # noqa: E402

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07]*\x07")
CURL_PROGRESS_RE = re.compile(
    r"^\s*(% Total|\d{1,3}\s+[\d.]+[kMG]?\s+\d{1,3}\s|Dload|\s*\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+\s+\d+)")


def write_helpers() -> Path:
    bindir = core.DATA_DIR / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    askpass = bindir / "allyhub-askpass"
    askpass.write_text(
        "#!/bin/sh\n"
        "MSG='Ally Hub needs your password (sudo) to continue:'\n"
        "if command -v kdialog >/dev/null 2>&1; then exec kdialog --title 'Ally Hub' --password \"$MSG\"\n"
        "elif command -v zenity >/dev/null 2>&1; then exec zenity --password --title='Ally Hub'\n"
        "fi\nexit 1\n")
    shim = bindir / "sudo"
    shim.write_text("#!/bin/sh\nexec /usr/bin/sudo -A \"$@\"\n")
    for f in (askpass, shim):
        f.chmod(0o755)
    return bindir


class JobRunner(QObject):
    output = Signal(str)
    started = Signal(str)
    finished = Signal(str, int, str)
    idle = Signal()

    def __init__(self, bindir: Path):
        super().__init__()
        self.queue, self.proc, self.current, self.tail = [], None, None, []
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PATH", f"{bindir}:{env.value('PATH', '/usr/bin:/bin')}")
        env.insert("SUDO_ASKPASS", str(bindir / "allyhub-askpass"))
        env.insert("TERM", "dumb")
        self.env = env

    def busy(self) -> bool:
        return self.proc is not None

    def pending_keys(self) -> set:
        keys = {k for _, _, k in self.queue}
        if self.current:
            keys.add(self.current[1])
        return keys

    def submit(self, label: str, cmd: str, key: str = ""):
        self.queue.append((label, cmd, key or label))
        if not self.busy():
            self._next()

    def _next(self):
        if not self.queue:
            self.current = None
            self.idle.emit()
            return
        label, cmd, key = self.queue.pop(0)
        self.current, self.tail = (label, key), []
        self.log_file = None
        try:
            core.JOB_LOG_DIR.mkdir(parents=True, exist_ok=True)
            self.log_file = open(core.job_log_path(key), "w", errors="replace")
            self.log_file.write(f"=== {label} ({time.strftime('%Y-%m-%d %H:%M:%S')}) ===\n$ {cmd}\n")
        except OSError:
            self.log_file = None
        self.proc = QProcess(self)
        self.proc.setProcessEnvironment(self.env)
        self.proc.setWorkingDirectory(str(HOME))
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        self.proc.readyReadStandardOutput.connect(self._read)
        self.proc.finished.connect(self._done)
        self.proc.errorOccurred.connect(self._error)
        self.output.emit(f"\n━━━ {label} ━━━\n$ {cmd}\n")
        self.started.emit(label)
        self.proc.start("bash", ["-c", cmd])

    def _read(self):
        data = ANSI_RE.sub("", bytes(self.proc.readAllStandardOutput()).decode("utf-8", "replace"))
        lines = [ln.split("\r")[-1] for ln in data.split("\n")]
        lines = [ln for ln in lines if not CURL_PROGRESS_RE.match(ln)]
        text = "\n".join(lines)
        if self.log_file:
            try:
                self.log_file.write(text if text.endswith("\n") else text + "\n")
                self.log_file.flush()
            except (OSError, ValueError):
                pass
        if text.strip():
            self.tail = (self.tail + [ln for ln in lines if ln.strip()])[-12:]
            self.output.emit(text if text.endswith("\n") else text + "\n")

    def _error(self, err):
        if err == QProcess.FailedToStart:
            self.output.emit("Failed to start bash.\n")
            self._done(127)

    def _done(self, code, _status=None):
        if self.proc is None:
            return
        _label, key = self.current
        self.output.emit(f"[{'done' if code == 0 else f'failed, exit code {code}'}]\n")
        if getattr(self, "log_file", None):
            try:
                self.log_file.write(f"[exit code {code}]\n")
                self.log_file.close()
            except (OSError, ValueError):
                pass
            self.log_file = None
        self.proc.deleteLater()
        self.proc = None
        self.finished.emit(key, code, "\n".join(self.tail))
        self._next()


# ==========================================================================
# Controller navigation (reads /dev/input/js*, no extra libraries)
# ==========================================================================

JS_EVENT = struct.Struct("<IhBB")
UP, DOWN, LEFT, RIGHT = "up", "down", "left", "right"


class GamepadNav(QObject):
    def __init__(self, hub):
        super().__init__(hub)
        self.hub = hub
        self.devs = {}
        self.axis = {}
        self.held = None
        self.repeat = QTimer(self)
        self.repeat.timeout.connect(self._repeat)
        self.stick_y = 0                 # right stick: free scrolling of the page
        self.stick = QTimer(self)
        self.stick.timeout.connect(self._stick_scroll)
        self.scan_timer = QTimer(self)
        self.scan_timer.timeout.connect(self.scan)
        self.enabled = False

    def set_enabled(self, on: bool):
        self.enabled = on
        if on:
            self.scan()
            self.scan_timer.start(3000)
        else:
            self.scan_timer.stop()
            for path in list(self.devs):
                self._close(path)

    def scan(self):
        for path in sorted(Path("/dev/input").glob("js*")):
            p = str(path)
            if p in self.devs:
                continue
            try:
                fd = os.open(p, os.O_RDONLY | os.O_NONBLOCK)
            except OSError:
                continue
            n = QSocketNotifier(fd, QSocketNotifier.Read, self)
            n.activated.connect(lambda *_a, path=p: self._read(path))
            self.devs[p] = (fd, n)

    def _close(self, path):
        fd, n = self.devs.pop(path)
        n.setEnabled(False)
        n.deleteLater()
        try:
            os.close(fd)
        except OSError:
            pass

    def _read(self, path):
        fd, _ = self.devs.get(path, (None, None))
        if fd is None:
            return
        try:
            data = os.read(fd, JS_EVENT.size * 64)
        except BlockingIOError:
            return
        except OSError:
            self._close(path)
            return
        for i in range(0, len(data) - JS_EVENT.size + 1, JS_EVENT.size):
            _t, value, etype, number = JS_EVENT.unpack_from(data, i)
            if etype & 0x80:          # initial state events
                continue
            if QApplication.activeWindow() is None:
                continue
            if etype & 0x01:
                self._button(number, value)
            elif etype & 0x02:
                self._axis(number, value)

    def _sheet_open(self) -> bool:
        return getattr(self.hub, "_sheet", None) is not None

    def _button(self, n, value):
        dpad = {11: LEFT, 12: RIGHT, 13: UP, 14: DOWN}
        if self._sheet_open() and n in (2, 3, 4, 5, 7):    # a pop-up is open: page shortcuts wait
            return
        if n in dpad:
            return self._direction(dpad[n] if value else None, f"b{n}")
        if not value:
            return
        if n == 0:
            self.activate()
        elif n == 1:
            self.back()
        elif n == 2:
            self.hub.gamepad_x()
        elif n == 3:
            self.hub.refresh()
            self.hub.toast("Refreshed")
        elif n in (4, 5):
            self.hub.step_page(-1 if n == 4 else 1)
        elif n == 7:
            QDesktopServices.openUrl(QUrl("steam://open/keyboard"))

    def _axis(self, n, value):
        if self._sheet_open() and n in (2, 3, 5):          # triggers wait for the pop-up
            return
        if n in (2, 5):                 # LT / RT switch sections inside a tab
            pressed = value > 8000
            was = self.axis.get(f"t{n}", False)
            self.axis[f"t{n}"] = pressed
            if pressed and not was:
                self.hub.step_sub(-1 if n == 2 else 1)
            return
        if n == 4:                      # right stick up/down scrolls the page, like a browser
            self.stick_y = value if abs(value) > 7000 else 0
            if self.stick_y and not self.stick.isActive():
                self.stick.start(16)
            elif not self.stick_y:
                self.stick.stop()
            return
        if n in (0, 6):
            d = LEFT if value < -16000 else RIGHT if value > 16000 else None
            self._direction(d, f"a{n}")
        elif n in (1, 7):
            d = UP if value < -16000 else DOWN if value > 16000 else None
            self._direction(d, f"a{n}")

    def _direction(self, d, source):
        prev = self.axis.get(source)
        self.axis[source] = d
        if d and d != prev:
            self.held = d
            self.move(d)
            self.repeat.start(380)
        elif not d and self.held and not any(v for k, v in self.axis.items() if not k.startswith("t")):
            self.held = None
            self.repeat.stop()

    def _repeat(self):
        if self.held:
            self.move(self.held)
            self.repeat.start(110)

    # ---- scrolling ----
    def scroll_area(self, w=None):
        """The scroll area that holds w (or the current page when w is None)."""
        p = w.parentWidget() if w is not None else None
        for _ in range(64):                  # widget trees are shallow; the cap guards odd parents
            if p is None or isinstance(p, QScrollArea):
                break
            p = p.parentWidget()
        if isinstance(p, QScrollArea):
            return p
        if QApplication.activeWindow() is self.hub:     # never scroll the app behind a dialog
            page = self.hub.current_page() if hasattr(self.hub, "current_page") else None
            if page is not None:
                return page if isinstance(page, QScrollArea) else page.findChild(QScrollArea)
        return None

    def scroll_by(self, area, dy: int) -> bool:
        """Scroll an area by dy pixels. False if it was already at that end."""
        if area is None:
            return False
        bar = area.verticalScrollBar()
        before = bar.value()
        bar.setValue(before + dy)
        return bar.value() != before

    def _step(self, area) -> int:
        return max(120, int(area.viewport().height() * 0.6)) if area is not None else 120

    def _stick_scroll(self):
        if not self.stick_y or QApplication.activeWindow() is None:
            self.stick.stop()
            return
        sheet = getattr(self.hub, "_sheet", None)
        if sheet is not None:                    # a pop-up is open: scroll it (or nothing), never the page
            area = sheet.findChild(QScrollArea)
        else:
            w = QApplication.focusWidget()
            area = self.scroll_area(w if w is not None and w not in self.hub.tab_buttons else None)
        self.scroll_by(area, int(self.stick_y / 32767 * 28))

    # ---- focus logic ----
    def _key(self, w, key):
        for etype in (QEvent.KeyPress, QEvent.KeyRelease):
            QApplication.sendEvent(w, QKeyEvent(etype, key, Qt.NoModifier))

    @staticmethod
    def _step_combo(w, d) -> bool:
        """Left/Right pick the previous/next option without opening the list. Combos marked
        padCycle=False (where a step would act at once, like turning controller navigation off) only change
        through A + the list. Returns True if the press was used."""
        if w.property("padCycle") is False or not w.count():
            return False
        i = max(0, min(w.count() - 1, w.currentIndex() + (1 if d == RIGHT else -1)))
        if i != w.currentIndex():
            w.setCurrentIndex(i)
            w.activated.emit(i)
        return True

    @staticmethod
    def _popup_view():
        """The list inside an open drop-down (combo box popup), if one is open."""
        popup = QApplication.activePopupWidget()
        if popup is None:
            return None
        return popup if isinstance(popup, QAbstractItemView) else popup.findChild(QAbstractItemView)

    def move(self, d):
        view = self._popup_view()
        if view is not None:                     # an open drop-down list: the pad scrolls through it
            if d in (UP, DOWN):
                self._key(view, Qt.Key_Up if d == UP else Qt.Key_Down)
            return
        w = QApplication.focusWidget()
        win = QApplication.activeWindow()
        if win is None:
            return
        sheet = getattr(self.hub, "_sheet", None)
        if sheet is not None and win is self.hub:   # an in-window dialog: stay inside it
            if w is None or not sheet.isAncestorOf(w):
                _focus_first(sheet)
                return
            if isinstance(w, QComboBox) and d in (LEFT, RIGHT) and self._step_combo(w, d):
                return
            target = self._nearest(w, win, d, root=sheet)
            if target is not None:
                target.setFocus(Qt.OtherFocusReason)
            return
        if w is None or w.window() is not win:
            if win is self.hub:
                self.hub.focus_tabs()
            return
        if isinstance(w, QAbstractItemView) and d in (UP, DOWN):
            self._key(w, Qt.Key_Up if d == UP else Qt.Key_Down)
            return
        if isinstance(w, QAbstractScrollArea) and not isinstance(w, QScrollArea) and d in (UP, DOWN):
            # text boxes (changelog, activity log): read through them first, then move on
            if self.scroll_by(w, (-1 if d == UP else 1) * self._step(w)):
                return
        side = getattr(self.hub, "bars", "top") == "sides"
        into_page, to_tabs = (RIGHT, LEFT) if side else (DOWN, UP)
        if win is self.hub and w in self.hub.tab_buttons and d == into_page:
            self.hub.focus_page()
            return
        if isinstance(w, QSlider) and d in (LEFT, RIGHT):
            step = max(1, (w.maximum() - w.minimum()) // 20)
            w.setValue(w.value() + (step if d == RIGHT else -step))
            return
        if isinstance(w, QSpinBox) and d in (LEFT, RIGHT):
            w.setValue(w.value() + (w.singleStep() if d == RIGHT else -w.singleStep()))
            return
        if isinstance(w, QComboBox) and d in (LEFT, RIGHT) and self._step_combo(w, d):
            return
        target = self._nearest(w, win, d)
        area = self.scroll_area(w)
        if d in (UP, DOWN) and area is not None and self._too_far(area, target, d):
            # nothing to select nearby (text, charts, results): scroll so it can be read, then keep going
            if self.scroll_by(area, (-1 if d == UP else 1) * self._step(area)):
                return
        if target is None:
            if d == to_tabs and win is self.hub:
                self.hub.focus_tabs()
            return
        target.setFocus(Qt.OtherFocusReason)
        tarea = self.scroll_area(target)
        if tarea is not None:
            tarea.ensureWidgetVisible(target, 40, 90)

    @staticmethod
    def _too_far(area, target, d) -> bool:
        """True when the next control is off screen by more than most of a screen (or there is none),
        so jumping to it would skip what's in between."""
        vp = area.viewport()
        if target is None or area.widget() is None or not area.widget().isAncestorOf(target):
            return True
        top = target.mapTo(area.widget(), QPoint(0, 0)).y()
        view_top = area.verticalScrollBar().value()
        view_h = vp.height()
        if d == DOWN:
            return top + target.height() > view_top + view_h * 1.6
        return top < view_top - view_h * 0.6

    @staticmethod
    def _nearest(w, win, d, root=None):
        def center(x):
            r = x.rect()
            return x.mapToGlobal(r.center())
        c0 = center(w)
        best, best_score = None, None
        for c in (root or win).findChildren(QWidget):
            if c is w or not c.isVisible() or not c.isEnabled():
                continue
            if not (c.focusPolicy() & Qt.TabFocus) or c.window() is not win:
                continue
            if isinstance(c, QScrollArea) or c.focusProxy() is not None:
                continue
            if isinstance(c.parentWidget(), QComboBox):
                continue
            p = center(c)
            dx, dy = p.x() - c0.x(), p.y() - c0.y()
            if d == DOWN and dy > 8:
                score = dy + 3 * abs(dx)
            elif d == UP and dy < -8:
                score = -dy + 3 * abs(dx)
            elif d == RIGHT and dx > 8:
                score = dx + 3 * abs(dy)
            elif d == LEFT and dx < -8:
                score = -dx + 3 * abs(dy)
            else:
                continue
            if best_score is None or score < best_score:
                best, best_score = c, score
        return best

    def activate(self):
        view = self._popup_view()
        if view is not None:                     # A picks the highlighted option in an open list
            self._key(view, Qt.Key_Return)
            return
        w = QApplication.focusWidget()
        sheet = getattr(self.hub, "_sheet", None)
        if sheet is not None and QApplication.activeWindow() is self.hub and (w is None or not sheet.isAncestorOf(w)):
            _focus_first(sheet)                  # never click something behind the pop-up
            return
        if w is None:
            return
        if w in self.hub.tab_buttons:
            self.hub.focus_page()
        elif isinstance(w, QAbstractItemView):
            self._key(w, Qt.Key_Return)
        elif isinstance(w, QAbstractButton):
            w.animateClick()
        elif isinstance(w, QComboBox):
            w.showPopup()
        elif isinstance(w, (QLineEdit, QSpinBox)):
            QDesktopServices.openUrl(QUrl("steam://open/keyboard"))

    def back(self):
        popup = QApplication.activePopupWidget()
        if popup is not None:
            popup.close()
            return
        sheet = getattr(self.hub, "_sheet", None)
        if sheet is not None and QApplication.activeWindow() is self.hub:   # B closes the in-window pop-up
            sheet.reject()
            return
        win = QApplication.activeWindow()
        if isinstance(win, QDialog):
            win.reject()
        elif QApplication.focusWidget() not in self.hub.tab_buttons:
            self.hub.focus_tabs()


# ==========================================================================
# Widget helpers
# ==========================================================================

def label(text: str, obj: str = "", wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if obj:
        lb.setObjectName(obj)
    lb.setWordWrap(wrap)
    return lb


# Line icons from Lucide (https://lucide.dev). ISC License, Copyright (c) Lucide Icons and Contributors.
# Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee is
# hereby granted, provided that the above copyright notice and this permission notice appear in all copies.
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE
# INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE
# FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
# OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING
# OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
# Inner SVG of each 24x24 icon; rendered by icon_pixmap() in the badge color scheme.
ICONS = {
    'blocks': '<path d="M10 22V7a1 1 0 0 0-1-1H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5a1 1 0 0 0-1-1H2" /><rect x="14" y="2" width="8" height="8" rx="1" />',
    'palette': '<path d="M12 22a1 1 0 0 1 0-20 10 9 0 0 1 10 9 5 5 0 0 1-5 5h-2.25a1.75 1.75 0 0 0-1.4 2.8l.3.4a1.75 1.75 0 0 1-1.4 2.8z" /><circle cx="13.5" cy="6.5" r=".5" fill="currentColor" /><circle cx="17.5" cy="10.5" r=".5" fill="currentColor" /><circle cx="6.5" cy="12.5" r=".5" fill="currentColor" /><circle cx="8.5" cy="7.5" r=".5" fill="currentColor" />',
    'stethoscope': '<path d="M11 2v2" /><path d="M5 2v2" /><path d="M5 3H4a2 2 0 0 0-2 2v4a6 6 0 0 0 12 0V5a2 2 0 0 0-2-2h-1" /><path d="M8 15a6 6 0 0 0 12 0v-3" /><circle cx="20" cy="10" r="2" />',
    'monitor-play': '<path d="M15.033 9.44a.647.647 0 0 1 0 1.12l-4.065 2.352a.645.645 0 0 1-.968-.56V7.648a.645.645 0 0 1 .967-.56z" /><path d="M12 17v4" /><path d="M8 21h8" /><rect x="2" y="3" width="20" height="14" rx="2" />',
    'lightbulb': '<path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5" /><path d="M9 18h6" /><path d="M10 22h4" />',
    'sparkles': '<path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z" /><path d="M20 2v4" /><path d="M22 4h-4" /><circle cx="4" cy="20" r="2" />',
    'bot': '<path d="M12 8V4H8" /><rect width="16" height="12" x="4" y="8" rx="2" /><path d="M2 14h2" /><path d="M20 14h2" /><path d="M15 13v2" /><path d="M9 13v2" />',
    'save': '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" /><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7" /><path d="M7 3v4a1 1 0 0 0 1 1h7" />',
    'power': '<path d="M12 2v10" /><path d="M18.4 6.6a9 9 0 1 1-12.77.04" />',
    'globe': '<circle cx="12" cy="12" r="10" /><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" /><path d="M2 12h20" />',
    'smartphone': '<rect width="14" height="20" x="5" y="2" rx="2" ry="2" /><path d="M12 18h.01" />',
    'battery-charging': '<path d="m11 7-3 5h4l-3 5" /><path d="M14.856 6H16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.935" /><path d="M22 14v-4" /><path d="M5.14 18H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h2.936" />',
    'hard-drive': '<path d="M10 16h.01" /><path d="M2.212 11.577a2 2 0 0 0-.212.896V18a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-5.527a2 2 0 0 0-.212-.896L18.55 5.11A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z" /><path d="M21.946 12.013H2.054" /><path d="M6 16h.01" />',
    'file-down': '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z" /><path d="M14 2v5a1 1 0 0 0 1 1h5" /><path d="M12 18v-6" /><path d="m9 15 3 3 3-3" />',
    'terminal': '<path d="M12 19h8" /><path d="m4 17 6-6-6-6" />',
    'clapperboard': '<path d="m12.296 3.464 3.02 3.956" /><path d="M20.2 6 3 11l-.9-2.4c-.3-1.1.3-2.2 1.3-2.5l13.5-4c1.1-.3 2.2.3 2.5 1.3z" /><path d="M3 11h18v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" /><path d="m6.18 5.276 3.1 3.899" />',
    'archive': '<rect width="20" height="5" x="2" y="3" rx="1" /><path d="M4 8v11a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8" /><path d="M10 12h4" />',
    'refresh-cw': '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" /><path d="M21 3v5h-5" /><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" /><path d="M8 16H3v5" />',
    'bug': '<path d="M12 20v-9" /><path d="M14 7a4 4 0 0 1 4 4v3a6 6 0 0 1-12 0v-3a4 4 0 0 1 4-4z" /><path d="M14.12 3.88 16 2" /><path d="M21 21a4 4 0 0 0-3.81-4" /><path d="M21 5a4 4 0 0 1-3.55 3.97" /><path d="M22 13h-4" /><path d="M3 21a4 4 0 0 1 3.81-4" /><path d="M3 5a4 4 0 0 0 3.55 3.97" /><path d="M6 13H2" /><path d="m8 2 1.88 1.88" /><path d="M9 7.13V6a3 3 0 1 1 6 0v1.13" />',
    'key-round': '<path d="M2.586 17.414A2 2 0 0 0 2 18.828V21a1 1 0 0 0 1 1h3a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h1a1 1 0 0 0 1-1v-1a1 1 0 0 1 1-1h.172a2 2 0 0 0 1.414-.586l.814-.814a6.5 6.5 0 1 0-4-4z" /><circle cx="16.5" cy="7.5" r=".5" fill="currentColor" />',
    'lock-keyhole': '<circle cx="12" cy="16" r="1" /><rect x="3" y="10" width="18" height="12" rx="2" /><path d="M7 10V7a5 5 0 0 1 10 0v3" />',
    'download': '<path d="M12 15V3" /><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><path d="m7 10 5 5 5-5" />',
    'wrench': '<path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.106-3.105c.32-.322.863-.22.983.218a6 6 0 0 1-8.259 7.057l-7.91 7.91a1 1 0 0 1-2.999-3l7.91-7.91a6 6 0 0 1 7.057-8.259c.438.12.54.662.219.984z" />',
    'rotate-ccw': '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" /><path d="M3 3v5h5" />',
    'trash': '<path d="M10 11v6" /><path d="M14 11v6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" /><path d="M3 6h18" /><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />',
    'square-plus': '<rect width="18" height="18" x="3" y="3" rx="2" /><path d="M8 12h8" /><path d="M12 8v8" />',
    'gamepad-2': '<line x1="6" x2="10" y1="11" y2="11" /><line x1="8" x2="8" y1="9" y2="13" /><line x1="15" x2="15.01" y1="12" y2="12" /><line x1="18" x2="18.01" y1="10" y2="10" /><path d="M17.32 5H6.68a4 4 0 0 0-3.978 3.59c-.006.052-.01.101-.017.152C2.604 9.416 2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5 2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2 2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0 3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4 4 0 0 0 17.32 5z" />',
    'plug': '<path d="M12 22v-5" /><path d="M15 8V2" /><path d="M17 8a1 1 0 0 1 1 1v4a4 4 0 0 1-4 4h-4a4 4 0 0 1-4-4V9a1 1 0 0 1 1-1z" /><path d="M9 8V2" />',
    'gauge': '<path d="m12 14 4-4" /><path d="M3.34 19a10 10 0 1 1 17.32 0" />',
    'cpu': '<path d="M12 20v2" /><path d="M12 2v2" /><path d="M17 20v2" /><path d="M17 2v2" /><path d="M2 12h2" /><path d="M2 17h2" /><path d="M2 7h2" /><path d="M20 12h2" /><path d="M20 17h2" /><path d="M20 7h2" /><path d="M7 20v2" /><path d="M7 2v2" /><rect x="4" y="4" width="16" height="16" rx="2" /><rect x="8" y="8" width="8" height="8" rx="1" />',
    'rocket': '<path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" /><path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09" /><path d="M9 12a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.4 22.4 0 0 1-4 2z" /><path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 .05 5 .05" />',
    'joystick': '<path d="M21 17a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v2a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-2Z" /><path d="M6 15v-2" /><path d="M12 15V9" /><circle cx="12" cy="6" r="3" />',
    'gamepad': '<line x1="6" x2="10" y1="12" y2="12" /><line x1="8" x2="8" y1="10" y2="14" /><line x1="15" x2="15.01" y1="13" y2="13" /><line x1="18" x2="18.01" y1="11" y2="11" /><rect width="20" height="12" x="2" y="6" rx="2" />',
    'images': '<path d="m22 11-1.296-1.296a2.4 2.4 0 0 0-3.408 0L11 16" /><path d="M4 8a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2" /><circle cx="13" cy="7" r="1" fill="currentColor" /><rect x="8" y="2" width="14" height="14" rx="2" />',
    'swords': '<path d="m13 19 6-6" /><path d="M14.5 17.5 3.586 6.586A2 2 0 013 5.172V3h2.172a2 2 0 011.414.586L17.5 14.5" /><path d="m14.828 6.172 2.586-2.586A2 2 0 0118.828 3H21v2.172a2 2 0 01-.586 1.414l-2.586 2.586" /><path d="m16 16 4 4" /><path d="m19 21 2-2" /><path d="m5 14 4 4" /><path d="m5 21-2-2" /><path d="M7.5 16.5 4 20" />',
    'layout-grid': '<rect width="7" height="7" x="3" y="3" rx="1" /><rect width="7" height="7" x="14" y="3" rx="1" /><rect width="7" height="7" x="14" y="14" rx="1" /><rect width="7" height="7" x="3" y="14" rx="1" />',
    'wine': '<path d="M8 22h8" /><path d="M7 10h10" /><path d="M12 15v7" /><path d="M12 15a5 5 0 0 0 5-5c0-2-.5-4-2-8H9c-1.5 4-2 6-2 8a5 5 0 0 0 5 5Z" />',
    'store': '<path d="M15 21v-5a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v5" /><path d="M17.774 10.31a1.12 1.12 0 0 0-1.549 0 2.5 2.5 0 0 1-3.451 0 1.12 1.12 0 0 0-1.548 0 2.5 2.5 0 0 1-3.452 0 1.12 1.12 0 0 0-1.549 0 2.5 2.5 0 0 1-3.77-3.248l2.889-4.184A2 2 0 0 1 7 2h10a2 2 0 0 1 1.653.873l2.895 4.192a2.5 2.5 0 0 1-3.774 3.244" /><path d="M4 10.95V19a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8.05" />',
    'library': '<path d="m16 6 4 14" /><path d="M12 6v14" /><path d="M8 8v12" /><path d="M4 4v16" />',
    'atom': '<circle cx="12" cy="12" r="1" /><path d="M20.2 20.2c2.04-2.03.02-7.36-4.5-11.9-4.54-4.52-9.87-6.54-11.9-4.5-2.04 2.03-.02 7.36 4.5 11.9 4.54 4.52 9.87 6.54 11.9 4.5Z" /><path d="M15.7 15.7c4.52-4.54 6.54-9.87 4.5-11.9-2.03-2.04-7.36-.02-11.9 4.5-4.52 4.54-6.54 9.87-4.5 11.9 2.03 2.04 7.36.02 11.9-4.5Z" />',
    'circle-arrow-up': '<circle cx="12" cy="12" r="10" /><path d="m16 12-4-4-4 4" /><path d="M12 16V8" />',
    'wand-sparkles': '<path d="m21.64 3.64-1.28-1.28a1.21 1.21 0 0 0-1.72 0L2.36 18.64a1.21 1.21 0 0 0 0 1.72l1.28 1.28a1.2 1.2 0 0 0 1.72 0L21.64 5.36a1.2 1.2 0 0 0 0-1.72" /><path d="m14 7 3 3" /><path d="M5 6v4" /><path d="M19 14v4" /><path d="M10 2v2" /><path d="M7 8H3" /><path d="M21 16h-4" /><path d="M11 3H9" />',
    'cloud': '<path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" />',
    'compass': '<circle cx="12" cy="12" r="10" /><path d="m16.24 7.76-1.804 5.411a2 2 0 0 1-1.265 1.265L7.76 16.24l1.804-5.411a2 2 0 0 1 1.265-1.265z" />',
    'moon': '<path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401" />',
    'tv': '<path d="m17 2-5 5-5-5" /><rect width="20" height="15" x="2" y="7" rx="2" />',
    'pickaxe': '<path d="m14 13-8.381 8.38a1 1 0 0 1-3.001-3L11 9.999" /><path d="M15.973 4.027A13 13 0 0 0 5.902 2.373c-1.398.342-1.092 2.158.277 2.601a19.9 19.9 0 0 1 5.822 3.024" /><path d="M16.001 11.999a19.9 19.9 0 0 1 3.024 5.824c.444 1.369 2.26 1.676 2.603.278A13 13 0 0 0 20 8.069" /><path d="M18.352 3.352a1.205 1.205 0 0 0-1.704 0l-5.296 5.296a1.205 1.205 0 0 0 0 1.704l2.296 2.296a1.205 1.205 0 0 0 1.704 0l5.296-5.296a1.205 1.205 0 0 0 0-1.704z" />',
    'box': '<path d="M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" /><path d="m3.3 7 8.7 5 8.7-5" /><path d="M12 22V12" />',
    'message-circle': '<path d="M2.992 16.342a2 2 0 0 1 .094 1.167l-1.065 3.29a1 1 0 0 0 1.236 1.168l3.413-.998a2 2 0 0 1 1.099.092 10 10 0 1 0-4.777-4.719" />',
    'messages-square': '<path d="M16 10a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 14.286V4a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" /><path d="M20 9a2 2 0 0 1 2 2v10.286a.71.71 0 0 1-1.212.502l-2.202-2.202A2 2 0 0 0 17.172 19H10a2 2 0 0 1-2-2v-1" />',
    'music': '<path d="M9 18V5l12-2v13" /><circle cx="6" cy="18" r="3" /><circle cx="18" cy="16" r="3" />',
    'popcorn': '<path d="M18 8a2 2 0 0 0 0-4 2 2 0 0 0-4 0 2 2 0 0 0-4 0 2 2 0 0 0-4 0 2 2 0 0 0 0 4" /><path d="M10 22 9 8" /><path d="m14 22 1-14" /><path d="M20 8c.5 0 .9.4.8 1l-2.6 12c-.1.5-.7 1-1.2 1H7c-.6 0-1.1-.4-1.2-1L3.2 9c-.1-.6.3-1 .8-1Z" />',
    'activity': '<path d="M22 12h-2.48a2 2 0 0 0-1.93 1.46l-2.35 8.36a.25.25 0 0 1-.48 0L9.24 2.18a.25.25 0 0 0-.48 0l-2.35 8.36A2 2 0 0 1 4.49 12H2" />',
    'send': '<path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z" /><path d="m21.854 2.147-10.94 10.939" />',
    'video': '<path d="m16 13 5.223 3.482a.5.5 0 0 0 .777-.416V7.87a.5.5 0 0 0-.752-.432L16 10.5" /><rect x="2" y="6" width="14" height="12" rx="2" />',
    'shield-check': '<path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" /><path d="m9 12 2 2 4-4" />',
    'warehouse': '<path d="M18 21V10a1 1 0 0 0-1-1H7a1 1 0 0 0-1 1v11" /><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 1.132-1.803l7.95-3.974a2 2 0 0 1 1.837 0l7.948 3.974A2 2 0 0 1 22 8z" /><path d="M6 13h12" /><path d="M6 17h12" />',
    'package': '<path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z" /><path d="M12 22V12" /><polyline points="3.29 7 12 12 20.71 7" /><path d="m7.5 4.27 9 5.15" />',
    'film': '<rect width="18" height="18" x="3" y="3" rx="2" /><path d="M7 3v18" /><path d="M3 7.5h4" /><path d="M3 12h18" /><path d="M3 16.5h4" /><path d="M17 3v18" /><path d="M17 7.5h4" /><path d="M17 16.5h4" />',
    'memory-stick': '<path d="M12 12v-2" /><path d="M12 18v-2" /><path d="M16 12v-2" /><path d="M16 18v-2" /><path d="M2 11h1.5" /><path d="M20 18v-2" /><path d="M20.5 11H22" /><path d="M4 18v-2" /><path d="M8 12v-2" /><path d="M8 18v-2" /><rect x="2" y="6" width="20" height="10" rx="2" />',
    'zap': '<path d="M15.914 4a1.5 1.5 0 00-2.474-1.561l-9 9A1.5 1.5 0 005.5 14h4.002a.5.5 0 01.471.666L8.086 20a1.5 1.5 0 002.475 1.56l9-9A1.5 1.5 0 0018.5 10h-3.997a.5.5 0 01-.472-.667z" />',
    'settings': '<path d="M9.671 4.136a2.34 2.34 0 0 1 4.659 0 2.34 2.34 0 0 0 3.319 1.915 2.34 2.34 0 0 1 2.33 4.033 2.34 2.34 0 0 0 0 3.831 2.34 2.34 0 0 1-2.33 4.033 2.34 2.34 0 0 0-3.319 1.915 2.34 2.34 0 0 1-4.659 0 2.34 2.34 0 0 0-3.32-1.915 2.34 2.34 0 0 1-2.33-4.033 2.34 2.34 0 0 0 0-3.831A2.34 2.34 0 0 1 6.35 6.051a2.34 2.34 0 0 0 3.319-1.915" /><circle cx="12" cy="12" r="3" />',
}

# Catalog items get an icon for what they do (falls back to their category's icon)
ITEM_ICONS = {
    "decky": "plug", "allycenter": "gauge", "simpledeckytdp": "cpu", "nonsteamlaunchers": "rocket",
    "lsfg": "zap", "framegen": "sparkles",
    "tailscale": "globe", "emudeck": "joystick", "net.retrodeck.retrodeck": "gamepad",
    "com.steamgriddb.SteamROMManager": "images", "com.heroicgameslauncher.hgl": "swords",
    "net.lutris.Lutris": "layout-grid", "com.usebottles.bottles": "wine", "io.itch.itch": "store",
    "page.kramo.Cartridges": "library", "com.vysp3r.ProtonPlus": "atom",
    "net.davidotek.pupgui2": "circle-arrow-up", "com.github.Matoking.protontricks": "wand-sparkles",
    "io.github.unknownskl.greenlight": "cloud", "com.google.Chrome": "compass",
    "com.moonlight_stream.Moonlight": "moon", "io.github.streetpea.chiaki-ng": "tv",
    "org.vinegarhq.Sober": "blocks", "org.prismlauncher.PrismLauncher": "pickaxe", "io.mrarm.mcpelauncher": "box",
    "com.discordapp.Discord": "message-circle", "dev.vencord.Vesktop": "messages-square",
    "com.spotify.Client": "music", "tv.kodi.Kodi": "tv", "tv.plex.PlexHTPC": "film", "com.stremio.Stremio": "popcorn",
    "io.github.radiolamp.mangojuice": "activity", "com.github.mtkennerly.ludusavi": "save",
    "org.localsend.localsend_app": "send", "com.obsproject.Studio": "video",
    "com.github.tchx84.Flatseal": "shield-check", "io.github.flattool.Warehouse": "warehouse",
}
CATEGORY_ICONS = {"Essentials": "plug", "Game Mode plugins": "plug", "Launchers & stores": "rocket",
                  "Emulation": "joystick", "Game launchers": "gamepad-2", "Compatibility": "wrench",
                  "Cloud & streaming": "cloud", "More games": "gamepad-2", "Social & media": "music",
                  "Utilities": "wrench"}


def item_icon(item) -> str:
    return ITEM_ICONS.get(item.id) or CATEGORY_ICONS.get(getattr(item, "category", ""), "package")


def icon_pixmap(name: str, size: int, color: str = "#ffffff"):
    """A crisp Lucide line icon as a pixmap, or None if the icon or SVG support is missing."""
    body = ICONS.get(name)
    if not body:
        return None
    app = QApplication.instance()
    dpr = app.devicePixelRatio() if app else 1.0
    try:
        dpr = max(1.0, float(dpr))
    except (TypeError, ValueError):
        dpr = 1.0
    px = int(size * dpr)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{px}" height="{px}" viewBox="0 0 24 24" '
           f'fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
           f'{body}</svg>')
    pm = QPixmap()
    if not pm.loadFromData(svg.encode(), "SVG") or pm.isNull():
        return None
    pm.setDevicePixelRatio(dpr)
    return pm


def monogram_badge(text: str, color: str, size: int = 56) -> QLabel:
    """A colored rounded badge. `text` is an icon name from ICONS (drawn as a white line icon);
    anything else is shown as text, which is also the fallback if SVG rendering isn't available."""
    c = QColor(color)
    fg = "#111" if c.lightness() > 190 else "white"
    pm = icon_pixmap(text, int(size * 0.5), "#111111" if fg == "#111" else "#ffffff") if text in ICONS else None
    lb = QLabel("" if pm is not None else text)
    if pm is not None:
        lb.setPixmap(pm)
    elif text in ICONS:
        lb.setText(text[:1].upper())
    lb.setFixedSize(size, size)
    lb.setAlignment(Qt.AlignCenter)
    lb.setStyleSheet(
        f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {c.lighter(115).name()}, "
        f"stop:1 {c.darker(150).name()}); border-radius: {size // 3}px; "
        f"font-size: {max(12, size // 3 - (2 if len(text) > 2 else 0))}px; font-weight: 700; color: {fg};")
    return lb


def brand_icon(size: int) -> QLabel:
    """The Ally Hub app icon (same artwork as the GitHub repo), with a fallback."""
    path = core.APP_DIR / "allyhub.svg"
    lb = QLabel()
    lb.setFixedSize(size, size)
    pm = QIcon(str(path)).pixmap(QSize(size, size)) if path.exists() else None
    if pm is not None and not pm.isNull():
        lb.setPixmap(pm)
        return lb
    return monogram_badge("AH", "#e11d48", size)


def scroll_page(inner: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setWidget(inner)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.setFocusPolicy(Qt.NoFocus)
    QScroller.grabGesture(sa.viewport(), QScroller.TouchGesture)
    return sa


def page_shell(widget: QWidget, title: str, sub: str) -> QVBoxLayout:
    inner = QWidget()
    v = QVBoxLayout(inner)
    v.setContentsMargins(36, 32, 36, 32)
    v.setSpacing(12)
    widget._shell, widget._title, widget._sub = v, None, None     # so a page can take blocks from others
    if title:
        widget._title = label(title, "pageTitle")
        widget._sub = label(sub, "pageSub", wrap=True)
        v.addWidget(widget._title)
        v.addWidget(widget._sub)
        v.addSpacing(8)
    outer = QVBoxLayout(widget)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(scroll_page(inner))
    return v


# ---- pages built from blocks (1.4.0 reorganization) ----
# Every section is one existing page (it keeps its logic) with blocks from other objects added to it. A block is a
# plain widget built by its owner (SystemPage's battery card, AutomationPage's helper card, ...), so the owner's
# methods keep working on it wherever it's shown. Blocks are built parentless and placed exactly once.

def retitle(page: QWidget, title: str, sub: str = None):
    if getattr(page, "_title", None) is not None:
        page._title.setText(title)
        if sub is not None:
            page._sub.setText(sub)


def add_block(page: QWidget, widget: QWidget, index: int = None, heading: str = ""):
    """Add a block to a page_shell page: at index (0 = right under the title), or at the end (above the
    trailing stretch, so it doesn't drift to the bottom of the screen)."""
    v = page._shell
    if index is None:
        index = v.count()
        if index and v.itemAt(index - 1).spacerItem() is not None:
            index -= 1
    else:
        index += 3 if getattr(page, "_title", None) is not None else 0      # title, subtitle, spacing
    if heading:
        v.insertWidget(index, label(heading.upper(), "section"))
        index += 1
    v.insertWidget(index, widget)


def block(*widgets, heading: str = "", spacing: int = 12) -> QWidget:
    """Several widgets (or layouts) as one block, with an optional section heading."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(spacing)
    if heading:
        lay.addWidget(label(heading.upper(), "section"))
    for x in widgets:
        lay.addLayout(x) if isinstance(x, QLayout) else lay.addWidget(x)
    return w


# ---- Simple / Advanced (config theme.advanced, Simple by default: the owner's call) ----
_ADVANCED = []        # wrappers that only show in Advanced; their own contents keep their own visibility


def advanced_mode() -> bool:
    return bool(load_config()["theme"].get("advanced"))


def adv(widget: QWidget) -> QWidget:
    """Show this only in Advanced. Wraps it, so the widget's own show/hide logic is never overridden."""
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(widget)
    if not advanced_mode():
        box.hide()          # never setVisible(True) here: a parentless widget would open as its own window
    _ADVANCED.append(box)
    return box


def repolish(w: QWidget):
    w.style().unpolish(w)
    w.style().polish(w)


def set_pill(pill: QLabel, text: str, state: str):
    pill.setText(text)
    pill.setProperty("state", state)
    repolish(pill)


def card_frame() -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    return f


def two_col_grid() -> QGridLayout:
    g = QGridLayout()
    g.setSpacing(16)
    g.setColumnStretch(0, 1)
    g.setColumnStretch(1, 1)
    return g


def titled_card(mono: str, color: str, title: str, desc: str = "") -> tuple:
    card = card_frame()
    v = QVBoxLayout(card)
    v.setContentsMargins(22, 20, 22, 20)
    v.setSpacing(10)
    h = QHBoxLayout()
    h.addWidget(monogram_badge(mono, color, 48))
    h.addWidget(label(title, "cardTitle"), 1)
    v.addLayout(h)
    if desc:
        v.addWidget(label(desc, "cardDesc", wrap=True))
    return card, v


def button(text: str, fn=None, kind: str = "") -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    b.setCursor(Qt.PointingHandCursor)
    if fn:
        b.clicked.connect(fn)
    return b


def key_hints(pairs, vertical: bool = False) -> QWidget:
    """Row of controller keycaps, e.g. [("A", "Select"), ("B", "Back")]; a column of them when vertical."""
    w = QWidget()
    outer = QVBoxLayout(w) if vertical else QHBoxLayout(w)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(6)
    for i, (key, text) in enumerate(pairs):
        if i and not vertical:
            outer.addSpacing(10)
        h = QHBoxLayout() if vertical else outer
        h.addWidget(label(key, "key"))
        if text:
            h.addWidget(label(text, "keyText"))
        if vertical:
            h.addStretch()
            outer.addLayout(h)
    return w


PAD_KEYS = [("A", "Select"), ("B", "Back"), ("RS", "Scroll"), ("Y", "Refresh"), ("Menu", "Keyboard")]
TAB_ICONS = {"Home": "activity", "Store": "store", "Games": "gamepad-2", "Customize": "palette",
             "Settings": "settings"}


_HUB = None          # the main window, set by Hub.__init__; dialogs open inside it


def run_dialog(dlg) -> int:
    """Show a dialog as a panel inside the Ally Hub window, over a dimmed page, instead of a new window
    (the owner: no more extra windows). Falls back to a normal window if embedding isn't possible."""
    hub = _HUB
    if hub is None or not hub.isVisible() or getattr(hub, "_sheet", None) is not None:
        return dlg.exec()                       # nested or before the window shows: plain dialog
    overlay = None
    before = QApplication.focusWidget()
    if isinstance(dlg, QMessageBox):
        title = dlg.windowTitle()
        if title and title != APP_NAME and not dlg.informativeText():
            if dlg.textFormat() == Qt.MarkdownText:    # child pop-ups have no title bar: show the title
                dlg.setText(f"### {title}\n\n{dlg.text()}")
            else:
                dlg.setInformativeText(dlg.text())
                dlg.setText(f"<b>{title}</b>")
        for getter, setter in ((dlg.text, dlg.setText), (dlg.informativeText, dlg.setInformativeText)):
            body = getter()
            if len(body) > 700 and not dlg.detailedText() and dlg.textFormat() != Qt.MarkdownText:
                setter(body[:600].rstrip() + "…")      # long text goes in the scrolling details box,
                dlg.setDetailedText(body)              # so the buttons always stay on screen
    try:
        overlay = QWidget(hub)
        overlay.setObjectName("dimmer")
        overlay.setAttribute(Qt.WA_StyledBackground, True)
        overlay.setGeometry(hub.rect())
        lay = QVBoxLayout(overlay)
        lay.setContentsMargins(24, 24, 24, 24)
        dlg.setParent(overlay, Qt.Widget)
        dlg.setObjectName("sheet")
        dlg.setAttribute(Qt.WA_StyledBackground, True)
        dlg.setMaximumWidth(max(420, int(hub.width() * 0.8)))
        dlg.setMaximumHeight(max(300, int(hub.height() * 0.9)))
        lay.addWidget(dlg, 0, Qt.AlignCenter)
        overlay.show()
        overlay.raise_()
        hub._sheet = dlg
        QTimer.singleShot(0, lambda: _focus_first(dlg))
        return dlg.exec()
    except Exception:
        core.report_exception("gui-dialog")
        hub._sheet = None
        try:
            dlg.setParent(hub, Qt.Dialog)
        except Exception:
            pass
        return dlg.exec()
    finally:
        hub._sheet = None
        if overlay is not None:
            try:
                dlg.hide()
                dlg.setParent(None)             # the caller may still read the dialog's answers
            except Exception:
                pass
            overlay.hide()
            overlay.deleteLater()
            try:
                import shiboken6
                if before is not None and shiboken6.isValid(before) and before.isVisible():
                    before.setFocus(Qt.OtherFocusReason)     # back to where the controller was
            except Exception:
                pass


def _focus_first(dlg):
    """Put the controller's focus on the dialog's default button, or its first control."""
    try:
        default = next((b for b in dlg.findChildren(QPushButton) if b.isDefault() and b.isVisible()), None)
        if default is not None:
            default.setFocus(Qt.OtherFocusReason)
            return
        for w in dlg.findChildren(QWidget):
            if w.isVisible() and w.isEnabled() and (w.focusPolicy() & Qt.TabFocus):
                w.setFocus(Qt.OtherFocusReason)
                return
    except RuntimeError:
        pass


def _message(parent, icon, title, text, buttons=None) -> QMessageBox:
    box = QMessageBox(parent or _HUB)
    box.setIcon(icon)
    box.setWindowTitle(title or APP_NAME)
    box.setText(text)
    if buttons is not None:
        box.setStandardButtons(buttons)
    run_dialog(box)
    return box


def _wait_for_sheet(fn, title, text) -> bool:
    """A message that arrives while another pop-up is open (say, a background task finishing) waits for it
    to close, instead of opening as a separate window."""
    hub = _HUB
    if hub is not None and getattr(hub, "_sheet", None) is not None:
        QTimer.singleShot(400, lambda: fn(None, title, text))
        return True
    return False


def msg_info(parent, title, text):
    if not _wait_for_sheet(msg_info, title, text):
        _message(parent, QMessageBox.Information, title, text)


def msg_warn(parent, title, text):
    if not _wait_for_sheet(msg_warn, title, text):
        _message(parent, QMessageBox.Warning, title, text)


def msg_error(parent, title, text):
    if not _wait_for_sheet(msg_error, title, text):
        _message(parent, QMessageBox.Critical, title, text)


def ask(parent, text: str) -> bool:
    box = _message(parent, QMessageBox.Question, APP_NAME, text, QMessageBox.Yes | QMessageBox.No)
    clicked = box.clickedButton()
    return clicked is not None and box.standardButton(clicked) == QMessageBox.Yes


def ask_item(parent, title: str, prompt: str, items: list) -> tuple:
    """Pick one of a few options: a list of big buttons (D-pad + A), no drop-down."""
    dlg = QDialog(parent or _HUB)
    dlg.setWindowTitle(title)
    v = QVBoxLayout(dlg)
    v.setContentsMargins(24, 20, 24, 20)
    v.addWidget(label(prompt, "cardTitle", wrap=True))
    chosen = {"v": None}
    for it in items:
        b = button(it, lambda _=False, it=it: (chosen.__setitem__("v", it), dlg.accept()))
        v.addWidget(b)
    v.addWidget(button("Cancel", dlg.reject))
    ok = run_dialog(dlg) == QDialog.Accepted and chosen["v"] is not None
    return (chosen["v"] or "", ok)


SWATCHES = ["#ef4444", "#f97316", "#f59e0b", "#eab308", "#84cc16", "#22c55e", "#10b981", "#14b8a6",
            "#06b6d4", "#0ea5e9", "#3b82f6", "#6366f1", "#8b5cf6", "#a855f7", "#d946ef", "#ec4899",
            "#f43f5e", "#e11d48", "#ffffff", "#cbd5e1", "#64748b", "#ffb4a2", "#b5e48c", "#000000"]


def pick_color(parent, current: str, title: str) -> Optional[str]:
    """Controller-friendly color picker: a grid of swatch buttons (D-pad + A). The full color wheel is
    still one button away for touch or mouse."""
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    v = QVBoxLayout(dlg)
    v.setContentsMargins(24, 20, 24, 20)
    v.addWidget(label(title, "cardTitle"))
    grid = QGridLayout()
    grid.setSpacing(10)
    chosen = {"c": None}

    def take(c):
        chosen["c"] = c
        dlg.accept()
    first = None
    for n, c in enumerate(SWATCHES):
        b = QPushButton("✔" if c.lower() == (current or "").lower() else "")
        b.setFixedSize(56, 56)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(c)
        b.setStyleSheet(f"QPushButton {{ background: {c}; border: 2px solid #00000055; border-radius: 12px; "
                        f"color: {'#000' if c in ('#ffffff', '#cbd5e1', '#b5e48c', '#ffb4a2', '#eab308') else '#fff'}; "
                        f"font-size: 20px; min-height: 0; }} QPushButton:focus {{ border: 4px solid #ffffff; }}")
        b.clicked.connect(lambda _=False, c=c: take(c))
        grid.addWidget(b, n // 8, n % 8)
        first = first or b
    v.addLayout(grid)
    row = QHBoxLayout()

    def wheel():
        c = QColorDialog.getColor(QColor(current or "#ffffff"), dlg, title)
        if c.isValid():
            take(c.name())
    if not GAMEMODE:                             # the full color wheel is its own window: desktop only
        row.addWidget(button("More colors…", wheel))
    row.addStretch()
    row.addWidget(button("Cancel", dlg.reject))
    v.addLayout(row)
    return chosen["c"] if run_dialog(dlg) == QDialog.Accepted else None


class _Color:
    """Stands in for the QColor that QColorDialog returned, so callers keep working."""
    def __init__(self, hexstr):
        self._h = hexstr

    def isValid(self):
        return bool(self._h)

    def name(self):
        return self._h or "#000000"


def ask_color(current, parent, title):
    return _Color(pick_color(parent, current.name() if hasattr(current, "name") else str(current), title))


def ask_text(parent, title: str, prompt: str, text: str = "") -> tuple:
    """Text input inside the window that brings up the Steam keyboard in Game Mode."""
    dlg = QInputDialog(parent or _HUB)
    dlg.setWindowTitle(title)
    dlg.setLabelText(prompt)
    dlg.setTextValue(text)
    if GAMEMODE:
        QTimer.singleShot(150, lambda: QDesktopServices.openUrl(QUrl("steam://open/keyboard")))
    ok = run_dialog(dlg) == QDialog.Accepted
    return dlg.textValue(), ok


def file_dialog_options():
    """Game Mode can't drive the desktop's own file picker; Qt's picker works with the controller."""
    return QFileDialog.DontUseNativeDialog if GAMEMODE else QFileDialog.Option(0)


def clear_layout(layout):
    while layout.count():
        it = layout.takeAt(0)
        if it.widget():
            it.widget().deleteLater()
        elif it.layout():
            clear_layout(it.layout())


# ==========================================================================
# Catalog pages
# ==========================================================================

class ItemCard(QFrame):
    action = Signal(str, str)

    def __init__(self, item: Item):
        super().__init__()
        self.item = item
        self.setObjectName("card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 18)
        root.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(14)
        top.addWidget(monogram_badge(item_icon(item), item.color))
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(label(item.name, "cardTitle"))
        self.pill = label("", "pill")
        pr = QHBoxLayout()
        pr.addWidget(self.pill)
        pr.addStretch()
        titles.addLayout(pr)
        top.addLayout(titles, 1)
        root.addLayout(top)
        root.addWidget(label(item.desc, "cardDesc", wrap=True))
        if item.warn:
            root.addWidget(label("⚠ " + item.warn, "cardWarn", wrap=True))
        root.addStretch()
        btns = QHBoxLayout()
        self.btn_install = button("Run" if item.kind == "run" else "Install",
                                  lambda: self.action.emit(item.id, "install"), "primary")
        self.btn_open = button("Open", lambda: self.action.emit(item.id, "open"))
        self.btn_remove = button("Remove", lambda: self.action.emit(item.id, "uninstall"), "danger")
        # Decky plugins can be switched off without uninstalling (if one misbehaves, it's one tap away)
        self.btn_toggle = button("Turn off", lambda: self.action.emit(item.id, "enable" if self.off else "disable"))
        self.off = False
        btns.addWidget(self.btn_install)
        btns.addWidget(self.btn_open)
        btns.addStretch()
        btns.addWidget(self.btn_toggle)
        btns.addWidget(self.btn_remove)
        root.addLayout(btns)

    def update_state(self, installed: bool, missing_reqs: list, queued: bool, version: str = "",
                     off: bool = False):
        self.off = bool(off)
        self.btn_toggle.setVisible(installed and bool(self.item.decky_names))
        self.btn_toggle.setText("Turn on" if self.off else "Turn off")
        self.btn_toggle.setEnabled(not queued)
        if queued:
            set_pill(self.pill, "WORKING…", "busy")
        elif installed and self.off:
            set_pill(self.pill, "TURNED OFF", "off")
        elif self.item.kind == "run":
            set_pill(self.pill, "TOOL", "tool")
        elif installed:
            set_pill(self.pill, f"INSTALLED · v{version.lstrip('v')}" if version else "INSTALLED", "on")
        else:
            set_pill(self.pill, "NOT INSTALLED", "off")
        if self.item.kind != "run":
            self.btn_install.setText("Reinstall / Update" if installed else "Install")
            self.btn_install.setObjectName("" if installed else "primary")
            repolish(self.btn_install)
        self.btn_install.setEnabled(not queued and not missing_reqs)
        self.btn_install.setToolTip("Install first: " + ", ".join(missing_reqs) if missing_reqs else "")
        self.btn_open.setVisible(installed and bool(self.item.open_cmd))
        self.btn_remove.setVisible(installed and bool(self.item.uninstall))
        self.btn_remove.setEnabled(not queued)


class BrowsePage(QWidget):
    """Store > Browse (1.4.0): mods, apps and Decky plugins in one place. Filter chips pick what shows; the Decky
    plugin store is the StorePage, shown under its own chip. Every catalog card exists once (self.cards) and is
    moved between the filter views, so update_cards keeps them all current."""

    FILTERS = [("essentials", "Essentials"), ("mods", "Mods"), ("apps", "Apps"), ("plugins", "Decky plugins"),
               ("installed", "Installed")]

    def __init__(self, hub, store_page):
        super().__init__()
        self.hub = hub
        self.store_page = store_page
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QFrame()
        bar.setObjectName("chipBar")
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(36, 14, 36, 0)
        bh.setSpacing(10)
        self.chips = {}
        for key, text in self.FILTERS:
            c = button(text, lambda _=False, k=key: self.set_filter(k), "chip")
            c.setCheckable(True)
            self.chips[key] = c
            bh.addWidget(c)
        bh.addStretch()
        v.addWidget(bar)
        self.stack = QStackedWidget()
        self.inner = QWidget()
        cv = QVBoxLayout(self.inner)
        cv.setContentsMargins(36, 20, 36, 32)
        cv.setSpacing(12)
        self.title = label("", "pageTitle")
        self.sub = label("", "pageSub", wrap=True)
        cv.addWidget(self.title)
        cv.addWidget(self.sub)
        top = QHBoxLayout()
        self.btn_all = button("Install all essentials", hub.install_essentials, "primary")
        top.addWidget(self.btn_all)
        self.btn_plugins = button("Your Decky plugins", lambda: self.set_filter("plugins"))
        top.addWidget(self.btn_plugins)
        top.addStretch()
        cv.addLayout(top)
        self.list_v = QVBoxLayout()
        self.list_v.setSpacing(12)
        cv.addLayout(self.list_v)
        cv.addStretch()
        self.stack.addWidget(scroll_page(self.inner))
        self.stack.addWidget(store_page)
        v.addWidget(self.stack, 1)
        self.cards = {}
        for item in CATALOG:
            card = ItemCard(item)
            card.action.connect(hub.on_item_action)
            card.setParent(self.inner)
            card.hide()
            self.cards[item.id] = card
        self.filter = None
        self.set_filter("essentials")

    def groups(self, key: str) -> list:
        """[(heading, [items])] for a filter."""
        st = self.hub.state
        if key == "essentials":
            return [("", [i for i in CATALOG if i.recommended])]
        if key == "installed":
            return [("", [i for i in CATALOG if i.kind == "install" and i.check(st)])]
        cats = core.MOD_CATEGORIES if key == "mods" else core.APP_CATEGORIES
        return [(c, [i for i in CATALOG if i.category == c]) for c in cats]

    def set_filter(self, key: str):
        self.filter = key
        for k, c in self.chips.items():
            c.setChecked(k == key)
        if key == "plugins":
            self.stack.setCurrentIndex(1)
            self.store_page.ensure_loaded()
            self.store_page.refresh_state()
            return
        self.stack.setCurrentIndex(0)
        self.rebuild()

    def rebuild(self):
        key = self.filter
        if key in (None, "plugins"):
            return
        titles = {"essentials": ("Essentials", "The few things most handhelds want. Tap Install on what you'd like."),
                  "mods": ("Mods", "Game Mode plugins, launchers and emulation."),
                  "apps": ("Apps", "Hand-picked apps from Flathub, installed for your user (no password)."),
                  "installed": ("Installed", "Everything Ally Hub installed for you. Remove anything you don't use.")}
        t, sub = titles[key]
        self.title.setText(t)
        self.sub.setText(sub)
        self.btn_all.setVisible(key == "essentials" and any(
            i.recommended and not i.check(self.hub.state) for i in CATALOG))
        self.btn_plugins.setVisible(key == "installed")
        while self.list_v.count():                     # take the cards out; they're reused, never deleted
            it = self.list_v.takeAt(0)
            lay, w = it.layout(), it.widget()
            if lay is not None:
                while lay.count():
                    c = lay.takeAt(0).widget()
                    if c is not None:
                        c.hide()
                lay.deleteLater()
            elif w is not None:
                w.deleteLater()
        shown = 0
        for heading, items in self.groups(key):
            if not items:
                continue
            if heading:
                self.list_v.addWidget(label(heading.upper(), "section"))
            grid = two_col_grid()
            for n, item in enumerate(items):
                card = self.cards[item.id]
                grid.addWidget(card, n // 2, n % 2)
                card.show()
                shown += 1
            self.list_v.addLayout(grid)
        if not shown:
            self.list_v.addWidget(label("Nothing here yet.", "cardDesc"))

    def refresh(self):
        self.set_filter(self.filter or "essentials")


class StatTile(QFrame):
    def __init__(self, title: str, big: bool = False):
        super().__init__()
        self.setObjectName("card")
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 14)
        v.addWidget(label(title, "statLabel"))
        self.value = label("…", "bigValue" if big else "statValue", wrap=True)
        v.addWidget(self.value)


# ==========================================================================
# Home
# ==========================================================================

class GroupPage(QWidget):
    """A top-level tab: a row of section chips over a stack of pages."""

    def __init__(self, hub, sections: list):
        super().__init__()
        self.hub = hub
        self.names = [n for n, _ in sections]
        self.pages = [p for _, p in sections]
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        bar = QFrame()
        bar.setObjectName("chipBar")
        bh = QHBoxLayout(bar)
        bh.setContentsMargins(36, 18, 36, 0)
        bh.setSpacing(10)
        self.chips = []
        for i, name in enumerate(self.names):
            c = button(name, lambda _=False, i=i: self.select(i), "chip")
            c.setCheckable(True)
            self.chips.append(c)
            bh.addWidget(c)
        bh.addStretch()
        self.lt_rt = key_hints([("LT", ""), ("RT", "")])
        bh.addWidget(self.lt_rt)
        bar.setVisible(len(sections) > 1)
        self.hidden = set()
        v.addWidget(bar)
        self.stack = QStackedWidget()
        for p in self.pages:
            self.stack.addWidget(p)
        v.addWidget(self.stack, 1)
        self.index = 0

    def set_hidden(self, i: int, hidden: bool):
        """Hide a section's chip (Setup once it's done, Activity in Simple). go() can still open it."""
        self.hidden = getattr(self, "hidden", set())
        (self.hidden.add if hidden else self.hidden.discard)(i)
        self.chips[i].setVisible(not hidden)

    def visible_indexes(self) -> list:
        hidden = getattr(self, "hidden", set())
        return [i for i in range(len(self.pages)) if i not in hidden] or [0]

    def step(self, delta: int):
        """LT/RT: the next visible section."""
        vis = self.visible_indexes()
        if self.index in vis:
            self.select(vis[(vis.index(self.index) + delta) % len(vis)])
            return
        # on a hidden section (opened with go()): the nearest visible one in that direction
        ahead = [i for i in vis if (i > self.index if delta > 0 else i < self.index)]
        self.select((ahead[0] if delta > 0 else ahead[-1]) if ahead else (vis[0] if delta > 0 else vis[-1]))

    def select(self, i: int):
        self.index = i % len(self.pages)
        for n, c in enumerate(self.chips):
            c.setChecked(n == self.index)
        self.stack.setCurrentIndex(self.index)
        self.hub.on_page_shown(self.pages[self.index])

    def current(self):
        return self.pages[self.index]


# ==========================================================================
# Decky Plugin Store
# ==========================================================================

class StoreRow(QFrame):
    action = Signal(dict, str)

    def __init__(self, plugin: dict, store):
        super().__init__()
        self.plugin = plugin
        self.setObjectName("card")
        h = QHBoxLayout(self)
        h.setContentsMargins(16, 16, 16, 16)
        h.setSpacing(16)
        self.thumb = QLabel()
        self.thumb.setObjectName("thumb")
        self.thumb.setFixedSize(176, 99)
        self.thumb.setAlignment(Qt.AlignCenter)
        h.addWidget(self.thumb)
        store.load_image(plugin.get("image_url"), self.thumb)
        mid = QVBoxLayout()
        mid.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(label(plugin.get("name", "?"), "cardTitle"))
        self.pill = label("", "pill")
        top.addWidget(self.pill)
        top.addStretch()
        mid.addLayout(top)
        latest = core.store_latest_version(plugin)
        meta = f"by {plugin.get('author', '?')}"
        if latest:
            meta += f" · v{latest.get('name', '?')}"
        if plugin.get("downloads"):
            meta += f" · {plugin['downloads']:,} downloads"
        mid.addWidget(label(meta, "cardMeta"))
        desc = (plugin.get("description") or "").strip()
        mid.addWidget(label(desc[:217] + "…" if len(desc) > 220 else desc, "cardDesc", wrap=True))
        h.addLayout(mid, 1)
        btns = QVBoxLayout()
        self.btn_install = button("Install", lambda: self.action.emit(self.plugin, "install"), "primary")
        self.btn_remove = button("Remove", lambda: self.action.emit(self.plugin, "uninstall"), "danger")
        self.off = False
        self.btn_toggle = button("Turn off", lambda: self.action.emit(self.plugin, "enable" if self.off else "disable"))
        btns.addWidget(self.btn_install)
        btns.addWidget(self.btn_toggle)
        btns.addWidget(self.btn_remove)
        btns.addStretch()
        h.addLayout(btns)

    def update_state(self, installed: Optional[dict], queued: bool, decky_ok: bool, off: bool = False):
        latest = core.store_latest_version(self.plugin) or {}
        self.off = bool(off)
        self.btn_toggle.setVisible(bool(installed))
        self.btn_toggle.setText("Turn on" if self.off else "Turn off")
        self.btn_toggle.setEnabled(not queued)
        if queued:
            set_pill(self.pill, "WORKING…", "busy")
        elif installed and self.off:
            set_pill(self.pill, "TURNED OFF", "off")
        elif installed and installed.get("version") and latest.get("name") \
                and core.plugin_newer(latest["name"], installed["version"]):
            set_pill(self.pill, f"UPDATE {installed['version']} → {latest['name']}", "update")
        elif installed:
            set_pill(self.pill, "INSTALLED", "on")
        else:
            self.pill.setText("")
        self.btn_install.setText("Reinstall / Update" if installed else "Install")
        self.btn_install.setObjectName("" if installed else "primary")
        repolish(self.btn_install)
        self.btn_install.setEnabled(decky_ok and not queued)
        self.btn_remove.setVisible(bool(installed))
        self.btn_remove.setEnabled(not queued)


class StorePage(QWidget):
    MAX_ROWS = 40

    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self.plugins, self.rows, self.image_cache = [], [], {}
        self.waiting = []
        self.net = QNetworkAccessManager(self)
        v = page_shell(self, "Plugin Store",
                       "Browse the official Decky plugin store and install plugins "
                       "without leaving Ally Hub.")
        self.need_decky = QFrame()
        self.need_decky.setObjectName("banner")
        nl = QHBoxLayout(self.need_decky)
        nl.setContentsMargins(20, 14, 20, 14)
        nl.addWidget(label("Decky Loader isn't installed yet. Install it first.", "bannerText", wrap=True), 1)
        nl.addWidget(button("Install Decky", lambda: hub.on_item_action("decky", "install"), "primary"))
        v.addWidget(self.need_decky)
        mine, mv = titled_card("plug", "#8b5cf6", "Your plugins",
                               "Everything in Decky, however it was installed. Turn a plugin off if it misbehaves "
                               "(it stays installed), or remove it.")
        self.mine_box = QVBoxLayout()
        self.mine_box.setSpacing(6)
        mv.addLayout(self.mine_box)
        srow = QHBoxLayout()
        self.btn_safe = button("Turn all plugins off", self.safe_mode)
        srow.addWidget(self.btn_safe)
        srow.addStretch()
        mv.addLayout(srow)
        mv.addWidget(label("If Game Mode acts up after installing plugins, turn them all off, then back on one at a "
                           "time to find the culprit.", "cardMeta", wrap=True))
        self.mine_card = mine
        v.addWidget(mine)
        v.addWidget(label("STORE", "section"))
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search plugins…")
        self.search.setClearButtonEnabled(True)
        bar.addWidget(self.search, 1)
        self.chips = {}
        for key, text in (("featured", "Featured"), ("popular", "Most popular"),
                          ("new", "Newest"), ("installed", "Installed")):
            c = button(text, lambda _=False, k=key: self.set_filter(k), "chip")
            c.setCheckable(True)
            self.chips[key] = c
            bar.addWidget(c)
        v.addLayout(bar)
        self.status = label("Loading the store…", "pageSub")
        v.addWidget(self.status)
        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(12)
        v.addLayout(self.list_box)
        v.addStretch()
        self.filter = "featured"
        self.chips["featured"].setChecked(True)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(300)
        self.debounce.timeout.connect(self.rebuild)
        self.search.textChanged.connect(lambda _: self.debounce.start())
        self.loading = False

    def with_plugins(self, callback):
        """Run callback(plugins) once the store list is loaded."""
        if self.plugins:
            callback(self.plugins)
            return
        self.waiting.append(callback)
        self.ensure_loaded()

    def ensure_loaded(self):
        if self.plugins or self.loading:
            return
        self.loading = True
        req = QNetworkRequest(QUrl(core.DECKY_STORE_API))
        req.setHeader(QNetworkRequest.UserAgentHeader, f"AllyHub/{VERSION}")
        reply = self.net.get(req)
        reply.finished.connect(lambda r=reply: self._on_list(r))

    def _on_list(self, reply):
        self.loading = False
        if reply.error() != QNetworkReply.NoError:
            self.status.setText(f"Couldn't reach the plugin store: {reply.errorString()}")
        else:
            try:
                data = json.loads(bytes(reply.readAll()).decode("utf-8"))
                self.plugins = [p for p in data if p.get("visible", True)]
            except Exception as e:
                self.status.setText(f"Store returned something unexpected: {e}")
        reply.deleteLater()
        waiting, self.waiting = self.waiting, []
        for cb in waiting:
            cb(self.plugins)
        self.rebuild()

    def load_image(self, url: Optional[str], target: QLabel):
        if not url:
            return
        if url in self.image_cache:
            target.setPixmap(self.image_cache[url])
            return
        reply = self.net.get(QNetworkRequest(QUrl(url)))

        def done(r=reply, t=target, u=url):
            if r.error() == QNetworkReply.NoError:
                pm = QPixmap()
                if pm.loadFromData(bytes(r.readAll())):
                    pm = pm.scaled(176, 99, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    self.image_cache[u] = pm
                    try:
                        t.setPixmap(pm)
                    except RuntimeError:
                        pass
            r.deleteLater()
        reply.finished.connect(done)

    def set_filter(self, key: str):
        self.filter = key
        for k, c in self.chips.items():
            c.setChecked(k == key)
        self.rebuild()

    def show_mine(self):
        """Every installed Decky plugin with On/Off and Remove, store or not (HueSync, Ally Hub's panel, ...)."""
        clear_layout(self.mine_box)
        plugins = sorted(self.hub.state.get("decky", {}).values(), key=lambda i: i["name"].lower())
        off = set(self.hub.state.get("decky_off") or [])
        self.mine_card.setVisible(bool(plugins) or bool(core.read_json(core.DECKY_SAFE_MODE, None)))
        pending = self.hub.runner.pending_keys()
        for info in plugins:
            row = QHBoxLayout()
            name = info["name"]
            state = "off" if name in off else "on"
            pill = label("", "pill")
            set_pill(pill, "OFF" if state == "off" else "ON", state)
            pill.setFixedWidth(56)
            pill.setAlignment(Qt.AlignCenter)
            row.addWidget(pill)
            row.addWidget(label(name + (f"  v{info['version'].lstrip('v')}" if info.get("version") else ""),
                                "cardDesc"), 1)
            busy = ("decky-mine:" + name) in pending
            t = button("Turn on" if state == "off" else "Turn off",
                       lambda _=False, n=name, s=state: self.hub.toggle_decky([n], s == "on", "decky-mine:" + n))
            r = button("Remove", lambda _=False, i=info: self.hub.remove_decky(i), "danger")
            t.setEnabled(not busy)
            r.setEnabled(not busy)
            row.addWidget(t)
            row.addWidget(r)
            self.mine_box.addLayout(row)
        saved = core.read_json(core.DECKY_SAFE_MODE, None)
        self.btn_safe.setText("Turn them back on" if saved else "Turn all plugins off")
        self.btn_safe.setEnabled(bool(saved) or any(i["name"] not in off for i in plugins))

    def safe_mode(self, *_args):
        saved = core.read_json(core.DECKY_SAFE_MODE, None)
        if saved:
            self.hub.toggle_decky(saved, False, "decky-safe", after=lambda ok: ok and core.DECKY_SAFE_MODE.unlink(
                missing_ok=True))
            return
        off = set(self.hub.state.get("decky_off") or [])
        names = [i["name"] for i in self.hub.state.get("decky", {}).values() if i["name"] not in off]
        if not names or not ask(self, f"Turn off all {len(names)} plugins?\n\nThey stay installed. “Turn them back "
                                      "on” restores exactly these."):
            return
        core.write_json(core.DECKY_SAFE_MODE, names)
        self.hub.toggle_decky(names, True, "decky-safe", confirm=False)

    def installed_for(self, plugin: dict) -> Optional[dict]:
        return self.hub.state["decky"].get((plugin.get("name") or "").lower())

    def visible_plugins(self) -> list:
        q = self.search.text().strip().lower()
        plugins = self.plugins
        if q:
            plugins = [p for p in plugins if q in (p.get("name", "") + " " + (p.get("description") or "")
                                                    + " " + " ".join(p.get("tags") or [])).lower()]
        if self.filter == "featured" and not q:
            def rank(p):
                n = (p.get("name") or "").lower()
                for i, f in enumerate(core.FEATURED_PLUGINS):
                    if f in n:
                        return i
                return None
            plugins = sorted((p for p in plugins if rank(p) is not None), key=rank)
        elif self.filter == "popular":
            plugins = sorted(plugins, key=lambda p: -(p.get("downloads") or 0))
        elif self.filter == "new":
            plugins = sorted(plugins, key=lambda p: p.get("created") or "", reverse=True)
        elif self.filter == "installed":
            plugins = [p for p in plugins if self.installed_for(p)]
        return plugins

    def rebuild(self):
        clear_layout(self.list_box)
        self.rows = []
        if not self.plugins:
            self.refresh_state()
            return
        plugins = self.visible_plugins()
        shown = plugins[: self.MAX_ROWS]
        extra = f" (showing {len(shown)}, search to narrow down)" if len(plugins) > len(shown) else ""
        self.status.setText(f"{len(plugins)} plugins{extra}")
        for p in shown:
            row = StoreRow(p, self)
            row.action.connect(self.hub.on_store_action)
            self.list_box.addWidget(row)
            self.rows.append(row)
        self.refresh_state()

    def refresh_state(self):
        decky_ok = CATALOG_BY_ID["decky"].check(self.hub.state)
        self.need_decky.setVisible(not decky_ok)
        pending = self.hub.runner.pending_keys()
        for row in self.rows:
            key = "store:" + (row.plugin.get("name") or "")
            inst = self.installed_for(row.plugin)
            row.update_state(inst, key in pending, decky_ok,
                             off=bool(inst) and inst["name"] in set(self.hub.state.get("decky_off") or []))
        self.show_mine()


# ==========================================================================
# Lighting
# ==========================================================================

class RingPreview(QWidget):
    """Two animated joystick rings showing an effect."""

    def __init__(self, w: int, h: int):
        super().__init__()
        self.setFixedSize(w, h)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.effect = core.normalize_effect({"type": "static", "colors": ["#e11d48"]})
        self.brightness = 255
        self.t0 = time.monotonic()
        self.track = QColor("#2e3448")

    def set_effect(self, effect: dict, brightness: int = 255):
        self.effect = core.normalize_effect(effect)
        self.brightness = brightness
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        zones = core.zone_frames(self.effect, time.monotonic() - self.t0)
        k = self.brightness / 255
        w, h = self.width(), self.height()
        rad = min(h * 0.36, w * 0.17)
        pen_w = max(3.0, rad * 0.3)
        # four lighting zones: the left and right half of each stick ring (Qt angles: 1/16 degree,
        # 0 = 3 o'clock, counter-clockwise), so the left half spans 90..270 degrees
        for stick, cx in enumerate((w * 0.27, w * 0.73)):
            rect = QRectF(cx - rad, h / 2 - rad, rad * 2, rad * 2)
            p.setPen(QPen(self.track, pen_w))
            p.drawEllipse(rect)
            for half, start in ((0, 90), (1, -90)):
                r, g, b = zones[stick * 2 + half]
                color = QColor(int(r * k), int(g * k), int(b * k))
                glow = QColor(color)
                glow.setAlpha(70)
                p.setPen(QPen(glow, pen_w * 2.2))
                p.drawArc(rect, start * 16, 180 * 16)
                p.setPen(QPen(color, pen_w))
                p.drawArc(rect, start * 16, 180 * 16)


class CardButton(QPushButton):
    """A QPushButton that hosts a child layout (preset cards, theme cards).

    Two Qt traps squash these: a QPushButton's sizeHint ignores its child layout, and the app
    stylesheet's `QPushButton { min-height }` is re-applied every time the widget is polished
    (first show, theme change), silently replacing setFixedHeight/setMinimumHeight. On the
    handheld that turned 124px preset cards into ~40px strips. So the size lives here and is
    re-pinned after every polish/style change. Sizes are logical px (QT_SCALE_FACTOR scales them).
    """

    def __init__(self, height: int, min_width: int, max_width: int = 16777215):
        super().__init__()
        self._card_h, self._card_min_w, self._card_max_w = height, min_width, max_width
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._pin_size()

    def _pin_size(self):
        self.setMinimumSize(self._card_min_w, self._card_h)
        self.setMaximumSize(self._card_max_w, self._card_h)

    def sizeHint(self):
        return QSize(self._card_min_w, self._card_h)

    def minimumSizeHint(self):
        return QSize(self._card_min_w, self._card_h)

    def event(self, ev):
        handled = super().event(ev)
        if ev.type() in (QEvent.Polish, QEvent.StyleChange, QEvent.PolishRequest):
            self._pin_size()
        return handled


class PresetCard(CardButton):
    def __init__(self, name: str, effect: dict, fn):
        # 124 tall = 12 margin + 58 rings + 6 gap + ~38 name + 10 margin
        super().__init__(124, 176, 280)
        self.setObjectName("presetCard")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.effect = core.normalize_effect(effect)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(6)
        self.preview = RingPreview(150, 58)
        self.preview.set_effect(self.effect)
        lay.addWidget(self.preview, 0, Qt.AlignHCenter)
        nm = label(name, "presetName")
        nm.setAlignment(Qt.AlignHCenter)
        nm.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay.addWidget(nm)
        self.clicked.connect(fn)


class LightingPage(QWidget):
    """Lighting studio: presets, a full effect editor and live previews."""

    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        cfg = load_config()
        self.effect = core.base_effect(cfg) or core.normalize_effect({"type": "static", "colors": ["#e11d48"]})
        self.brightness = int((cfg.get("rgb") or {}).get("brightness", 255))
        self.leds = []
        self.enum_boxes = {}
        self._syncing = False
        v = page_shell(self, "Lighting studio",
                       "Pick a ready-made effect or build your own. Changes show on the rings right away.")

        self.empty = self._banner(
            "No ring lights were detected on this kernel. You can still design effects here, and "
            "Ally Center (Store → Mods) can drive the rings in Game Mode.", None, None)
        self.agent_banner = self._banner("Animated effects run in the background helper, which is off.",
                                         "Turn it on", hub.enable_agent)
        self.perm_banner = self._banner("Allow lighting changes without a password so effects can run.",
                                        "Allow", self.allow_access)
        for b in (self.empty, self.agent_banner, self.perm_banner):
            v.addWidget(b)

        hero = card_frame()
        hh = QHBoxLayout(hero)
        hh.setContentsMargins(24, 20, 24, 20)
        hh.setSpacing(24)
        self.big = RingPreview(300, 140)
        hh.addWidget(self.big)
        col = QVBoxLayout()
        col.setSpacing(8)
        self.name_label = label("", "bigValue")
        self.detail_label = label("", "cardDesc")
        col.addWidget(self.name_label)
        col.addWidget(self.detail_label)
        col.addWidget(label("BRIGHTNESS", "section"))
        self.bright = QSlider(Qt.Horizontal)
        self.bright.setRange(0, 255)
        self.bright.setValue(self.brightness)
        self.bright.valueChanged.connect(self.on_brightness)
        col.addWidget(self.bright)
        br = QHBoxLayout()
        br.addWidget(button("Save as my effect", self.save_custom, "primary"))
        br.addWidget(button("Lights off", lambda: self.bright.setValue(0)))
        br.addWidget(button("Match app theme", self.match_theme))
        self.btn_test = button("Test lights", self.test_lights)
        br.addWidget(self.btn_test)
        br.addWidget(button("Use HueSync instead", hub.use_huesync_lighting))
        br.addStretch()
        col.addLayout(br)
        self.live_label = label("", "cardDesc", wrap=True)   # what the rings are really doing
        col.addWidget(self.live_label)
        hh.addLayout(col, 1)
        v.addWidget(hero)

        v.addWidget(label("PRESETS", "section"))
        self.preset_cards = {}
        pg = QGridLayout()
        pg.setSpacing(12)
        for c in range(5):
            pg.setColumnStretch(c, 1)
        for n, (name, eff) in enumerate(core.PRESETS.items()):
            c = PresetCard(name, eff, lambda _=False, e=eff: self.set_effect(e))
            self.preset_cards[name] = c
            pg.addWidget(c, n // 5, n % 5)
        v.addLayout(pg)

        v.addWidget(label("YOUR EFFECTS", "section"))
        self.custom_grid = QGridLayout()
        self.custom_grid.setSpacing(12)
        self.custom_grid.setAlignment(Qt.AlignLeft)
        for c in range(5):
            self.custom_grid.setColumnStretch(c, 1)
        v.addLayout(self.custom_grid)
        cr = QHBoxLayout()
        self.custom_pick = QComboBox()
        cr.addWidget(self.custom_pick)
        self.btn_delete = button("Delete", self.delete_custom, "danger")
        cr.addWidget(self.btn_delete)
        cr.addStretch()
        self.custom_manage = QWidget()
        self.custom_manage.setLayout(cr)
        v.addWidget(self.custom_manage)
        self.custom_empty = label("Tweak an effect below and tap Save as my effect to keep it here.",
                                  "cardDesc", wrap=True)
        v.addWidget(self.custom_empty)

        v.addWidget(label("EDIT EFFECT", "section"))
        ed = card_frame()
        ev = QVBoxLayout(ed)
        ev.setContentsMargins(22, 18, 22, 18)
        ev.setSpacing(14)
        tr = QHBoxLayout()
        tr.setSpacing(8)
        self.type_chips = {}
        for key, meta in core.EFFECT_TYPES.items():
            c = button(meta["name"], lambda _=False, k=key: self.set_type(k), "chip")
            c.setCheckable(True)
            self.type_chips[key] = c
            tr.addWidget(c)
        tr.addStretch()
        ev.addLayout(tr)
        self.colors_row = QHBoxLayout()
        self.colors_row.setSpacing(10)
        self.colors_wrap = QWidget()
        self.colors_wrap.setLayout(self.colors_row)
        ev.addWidget(self.colors_wrap)
        self.speed_label = label("", "cardDesc")
        ev.addWidget(self.speed_label)
        self.speed = QSlider(Qt.Horizontal)
        self.speed.setRange(10, 400)
        self.speed.valueChanged.connect(self.on_speed)
        ev.addWidget(self.speed)
        self.param_label = label("", "cardDesc")
        ev.addWidget(self.param_label)
        self.param = QSlider(Qt.Horizontal)
        self.param.setRange(0, 100)
        self.param.valueChanged.connect(self.on_param)
        ev.addWidget(self.param)
        self.spiral_wrap = QWidget()          # Spiral-only settings
        sr = QHBoxLayout(self.spiral_wrap)
        sr.setContentsMargins(0, 0, 0, 0)
        sr.setSpacing(16)
        self.spiral_boxes = {}
        for key, title in (("direction", "Direction"), ("layout", "Sticks"), ("engine", "Style")):
            col = QVBoxLayout()
            col.addWidget(label(title, "cardDesc"))
            box = QComboBox()
            box.addItems([text for _, text in core.SPIRAL_OPTIONS[key]])
            box.activated.connect(lambda i, k=key: self.set_spiral(k, core.SPIRAL_OPTIONS[k][i][0]))
            col.addWidget(box)
            sr.addLayout(col)
            self.spiral_boxes[key] = box
        self.rainbow_box = QCheckBox("Rainbow colors")
        self.rainbow_box.toggled.connect(lambda on: self.set_spiral("rainbow", bool(on)))
        sr.addWidget(self.rainbow_box)
        sr.addStretch()
        ev.addWidget(self.spiral_wrap)
        self.spiral_note = label("", "cardMeta", wrap=True)
        ev.addWidget(self.spiral_note)
        self.enum_row = QHBoxLayout()
        self.enum_row.setSpacing(16)
        ev.addLayout(self.enum_row)
        v.addWidget(ed)

        v.addWidget(label("PERFORMANCE", "section"))
        pf = card_frame()
        ph = QHBoxLayout(pf)
        ph.setContentsMargins(22, 16, 22, 16)
        ph.setSpacing(12)
        ph.addWidget(label("Smoothness", "cardDesc"))
        self.fps = QComboBox()
        self.fps_values = [10, 20, 30]
        self.fps.addItems(["Battery friendly (10 fps)", "Smooth (20 fps)", "Silky (30 fps)"])
        self.fps.activated.connect(lambda i: self._save_lighting(fps=self.fps_values[i]))
        ph.addWidget(self.fps)
        ph.addSpacing(16)
        ph.addWidget(label("On battery", "cardDesc"))
        self.on_battery = QComboBox()
        self.battery_values = ["full", "slow", "static"]
        self.on_battery.addItems(["Keep full speed", "Slow down to save power", "Show a still color"])
        self.on_battery.activated.connect(lambda i: self._save_lighting(on_battery=self.battery_values[i]))
        ph.addWidget(self.on_battery)
        ph.addStretch()
        v.addWidget(pf)
        v.addWidget(label("Battery rings, per-game lighting and dock lighting are further down this page, "
                          "and override this while they're active.", "pageSub", wrap=True))
        v.addStretch()

        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(250)
        self.debounce.timeout.connect(self.apply)
        self.anim = QTimer(self)
        self.anim.timeout.connect(self._tick)
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self.update_live)
        self._test_prev = None
        self._test_results = []
        self.refresh()

    # ---- helpers ----
    def _banner(self, text, btn_text, fn) -> QFrame:
        f = QFrame()
        f.setObjectName("banner")
        h = QHBoxLayout(f)
        h.setContentsMargins(20, 12, 20, 12)
        h.addWidget(label(text, "bannerText", wrap=True), 1)
        if btn_text:
            h.addWidget(button(btn_text, fn, "primary"))
        f.hide()
        return f

    def _save_lighting(self, **kw):
        update_config(lambda c: c["lighting"].update(kw))
        self.hub.toast("Saved")

    def showEvent(self, ev):
        super().showEvent(ev)
        self.anim.start(40)
        self.live_timer.start(2000)
        self.update_live()

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self.anim.stop()
        self.live_timer.stop()

    def _tick(self):
        self.big.update()
        for c in self.preset_cards.values():
            c.preview.update()
        for i in range(self.custom_grid.count()):
            w = self.custom_grid.itemAt(i).widget()
            if isinstance(w, PresetCard):
                w.preview.update()

    # ---- state ----
    def refresh(self):
        cfg = load_config()
        self.leds = core.find_leds()
        has = bool(self.leds)
        self.empty.setVisible(not has)
        self.perm_banner.setVisible(has and not core.lighting_access_ok(self.leds))
        self.agent_banner.setVisible(has and core.is_animated(self.effect) and not core.agent_running())
        light = cfg.get("lighting") or {}
        self.fps.setCurrentIndex(self.fps_values.index(light.get("fps", 20))
                                 if light.get("fps", 20) in self.fps_values else 1)
        ob = light.get("on_battery", "slow")
        self.on_battery.setCurrentIndex(self.battery_values.index(ob) if ob in self.battery_values else 1)
        self.rebuild_custom(light.get("custom") or {})
        self.sync_editor()
        self.update_live()

    def rebuild_custom(self, custom: dict):
        clear_layout(self.custom_grid)
        for n, (name, eff) in enumerate(custom.items()):
            c = PresetCard(name, eff, lambda _=False, e=eff: self.set_effect(e))
            self.custom_grid.addWidget(c, n // 5, n % 5)
        for n in range(len(custom), 5):          # keep cards the same width as presets
            spacer = QWidget()
            spacer.setMinimumWidth(176)
            self.custom_grid.addWidget(spacer, 0, n)
        self.custom_pick.clear()
        self.custom_pick.addItems(list(custom))
        self.custom_manage.setVisible(bool(custom))
        self.custom_empty.setVisible(not custom)

    def sync_editor(self):
        """Push self.effect into every control without triggering saves."""
        self._syncing = True
        e = self.effect
        meta = core.EFFECT_TYPES[e["type"]]
        self.name_label.setText(core.effect_label(e))
        self.detail_label.setText(meta["name"] + ("" if e["type"] == "static" else f" · speed {e['speed']:.1f}×"))
        self.big.set_effect(e, self.brightness)
        for k, c in self.type_chips.items():
            c.setChecked(k == e["type"])
        for name, c in self.preset_cards.items():
            c.setChecked(core.normalize_effect(core.PRESETS[name]) == e)
        clear_layout(self.colors_row)
        lo, hi = meta["colors"]
        if hi:
            self.colors_row.addWidget(label("Colors", "cardDesc"))
            for i, hexc in enumerate(e["colors"]):
                b = button("", lambda _=False, i=i: self.pick_color(i), "swatch")
                b.setStyleSheet(f"QPushButton#swatch {{ background: {hexc}; border: 2px solid #2e3448; }}"
                                f"QPushButton#swatch:focus {{ border: 3px solid white; }}")
                self.colors_row.addWidget(b)
            if len(e["colors"]) < hi:
                self.colors_row.addWidget(button("+ Add color", self.add_color))
            if len(e["colors"]) > lo:
                self.colors_row.addWidget(button("− Remove", self.remove_color))
            self.colors_row.addStretch()
        spiral = e["type"] == "spiral"
        # the chip's spiral is rainbow only, so color pickers would do nothing there
        self.colors_wrap.setVisible(bool(hi) and not (spiral and (e.get("rainbow") or e.get("engine") == "chip")))
        self.spiral_wrap.setVisible(spiral)
        self.spiral_note.setVisible(spiral)
        if spiral:
            for key, box in self.spiral_boxes.items():
                ids = [o for o, _ in core.SPIRAL_OPTIONS[key]]
                box.setCurrentIndex(ids.index(e[key]))
            self.rainbow_box.setChecked(bool(e.get("rainbow")))
            chip = e.get("engine") == "chip"
            self.rainbow_box.setEnabled(not chip)
            self.spiral_note.setText(
                "The chip's own spiral: rainbow only, uses no battery, but only speed and direction "
                "apply." if chip else
                "Each ring has two lighting zones (its left and right half), so the colors flow "
                "around four zones. Color spread sets how much of the color wheel they cover.")
        animated = e["type"] != "static"
        self.speed_label.setText(f"Speed  {e['speed']:.1f}×")
        self.speed.setValue(int(e["speed"] * 100))
        for w in (self.speed_label, self.speed):
            w.setVisible(animated)
        self.param_label.setText(f"{meta['param']}  {int(e['param'] * 100)}%" if meta["param"] else "")
        self.param.setValue(int(e["param"] * 100))
        for w in (self.param_label, self.param):
            w.setVisible(bool(meta["param"]))
        self.bright.setValue(self.brightness)
        clear_layout(self.enum_row)
        self.enum_boxes = {}
        if self.leds and not animated:
            saved = (load_config().get("rgb") or {}).get("enums", {})
            for attr, (options, current) in self.leds[0].enums.items():
                w = QWidget()
                wl = QVBoxLayout(w)
                wl.setContentsMargins(0, 0, 0, 0)
                wl.addWidget(label(f"Hardware {attr}", "cardDesc"))
                box = QComboBox()
                box.addItems(options)
                # default to plain-color mode: a hardware rainbow/breathe mode hides our colors
                box.setCurrentText(saved.get(attr) or core.static_mode(self.leds[0]).get(attr, current))
                box.currentTextChanged.connect(lambda _t: self.schedule())
                wl.addWidget(box)
                self.enum_row.addWidget(w)
                self.enum_boxes[attr] = box
            self.enum_row.addStretch()
        self.agent_banner.setVisible(bool(self.leds) and animated and not core.agent_running())
        self._syncing = False

    # ---- editing ----
    def set_effect(self, effect: dict):
        self.effect = core.normalize_effect(effect)
        if self.brightness == 0:
            self.brightness = 255
        self.sync_editor()
        self.schedule()

    def set_type(self, etype: str):
        e = dict(self.effect)
        if e["type"] != etype:
            e["type"] = etype
            e["param"] = core.EFFECT_DEFAULT_PARAM.get(etype, 0.5)
        self.set_effect(e)

    def set_spiral(self, key: str, value):
        if self._syncing or self.effect["type"] != "spiral":
            return
        self.set_effect(dict(self.effect, **{key: value}))

    def pick_color(self, i: int):
        if i >= len(self.effect["colors"]):
            return
        c = ask_color(QColor(self.effect["colors"][i]), self, "Pick a color")
        if c.isValid():
            e = dict(self.effect)
            e["colors"] = list(e["colors"])
            e["colors"][i] = c.name()
            self.set_effect(e)

    def add_color(self):
        e = dict(self.effect)
        used = set(e["colors"])
        e["colors"] = list(e["colors"]) + [next((c for c in core.DEFAULT_COLORS if c not in used), "#ffffff")]
        self.set_effect(e)

    def remove_color(self):
        e = dict(self.effect)
        e["colors"] = list(e["colors"])[:-1]
        self.set_effect(e)

    def on_speed(self, v):
        if self._syncing:
            return
        self.effect = core.normalize_effect(dict(self.effect, speed=v / 100))
        self.speed_label.setText(f"Speed  {self.effect['speed']:.1f}×")
        self.detail_label.setText(f"{core.EFFECT_TYPES[self.effect['type']]['name']} · speed {self.effect['speed']:.1f}×")
        self.big.set_effect(self.effect, self.brightness)
        self.schedule()

    def on_param(self, v):
        if self._syncing:
            return
        self.effect = core.normalize_effect(dict(self.effect, param=v / 100))
        meta = core.EFFECT_TYPES[self.effect["type"]]
        if meta["param"]:
            self.param_label.setText(f"{meta['param']}  {v}%")
        self.big.set_effect(self.effect, self.brightness)
        self.schedule()

    def on_brightness(self, v):
        if self._syncing:
            return
        self.brightness = v
        self.big.set_effect(self.effect, v)
        self.schedule()

    def match_theme(self):
        accent = core.theme_palette(load_config()["theme"])["accent"]
        self.set_effect({"type": "static", "colors": [accent]})

    def schedule(self):
        if not self._syncing:
            self.debounce.start()

    def save_custom(self):
        name, ok = ask_text(self, "Save effect", "Name your effect:", core.effect_label(self.effect))
        name = (name or "").strip()[:24]
        if not ok or not name:
            return
        if name in core.PRESETS:
            name += " (mine)"
        eff = self.effect
        update_config(lambda c: c["lighting"]["custom"].__setitem__(name, eff))
        self.rebuild_custom(load_config()["lighting"]["custom"])
        self.hub.toast(f"Saved “{name}”")

    def delete_custom(self):
        name = self.custom_pick.currentText()
        if name and ask(self, f"Delete “{name}”?"):
            update_config(lambda c: c["lighting"]["custom"].pop(name, None))
            self.rebuild_custom(load_config()["lighting"]["custom"])

    # ---- applying ----
    def apply(self):
        e = self.effect
        enums = {a: b.currentText() for a, b in self.enum_boxes.items()}
        first = core.hex_to_rgb(e["colors"][0]) if e["colors"] else None

        def fn(c):
            old = c.get("rgb") or {"rgb": [225, 29, 72]}
            c["rgb"] = {"rgb": list(first) if first else old.get("rgb", [225, 29, 72]),
                        "brightness": self.brightness, "enums": enums}
            c["lighting"]["effect"] = e
        update_config(fn)
        if not self.leds:
            return
        light = load_config()["lighting"]
        if light.get("encoding") == "hid":
            method = light.get("hid_method")
            if core.agent_running():
                # the agent draws it. Never write to the chip from two programs at once: their
                # packets interleave and the zones come out mixed
                self.hub.toast(f"{core.effect_label(e)} on")
                return
            if core.hid_streams(method) and core.is_animated(e) and not core.uses_chip_effect(e):
                self.agent_banner.show()                  # animation needs the background agent
                return
            if core.hid_apply_effect(e, self.brightness, self.leds, method):
                self.hub.toast(f"{core.effect_label(e)} on")
            else:
                self.hub.toast("Couldn't reach the lighting chip. Try Test lights.", 6000)
            return
        if e["type"] == "static":
            writes = []
            for led in self.leds:
                writes += core.rgb_writes(led, first, min(self.brightness, led.max_brightness), enums,
                                          load_config()["lighting"].get("encoding"))
            if core.try_direct_writes(writes):
                self.hub.toast("Lighting updated")
            else:
                # never a password prompt per tap: ask once for the permanent permission instead
                self.perm_banner.show()
                self.hub.toast("Tap Allow first so Ally Hub can change the lights.", 6000)
        elif core.agent_running():
            self.hub.toast(f"{core.effect_label(e)} on")
        else:
            self.agent_banner.show()
        QTimer.singleShot(2500, self.update_live)   # the agent picks the change up within ~1s

    # ---- what the rings are really doing ----
    OVERRIDES = {
        "battery rings": "battery rings", "game lighting": "this game's lighting",
        "docked": "dock lighting", "docked: lights off": "dock mode (lights off)",
        "low battery": "the low battery warning",
    }

    def live_text(self) -> str:
        if not self.leds:
            return ""
        st = core.agent_state()
        fresh = st and time.time() - float(st.get("ts") or 0) < 30
        reason = (st.get("led") or "") if fresh else ""
        if not core.agent_running() or not fresh:
            if core.is_animated(self.effect):
                return "Animated effects need the background helper, which isn't running."
            return ""
        if reason.startswith("no permission"):
            return "Ally Hub can't change the lights yet. Tap Allow at the top of this page."
        if reason == "can't write to the lights":
            return "The lights didn't accept the change. Tap Test lights to check them."
        if reason in self.OVERRIDES:
            return (f"Right now the rings show {self.OVERRIDES[reason]} (Automatic lighting, further down). "
                    "Your effect comes back when that ends.")
        if reason == "lights off":
            return "Lights are off. Pick an effect or raise the brightness to turn them on."
        if reason == "your lighting":
            return "✔ Your effect is on the rings."
        return ""

    def update_live(self):
        text = self.live_text()
        self.live_label.setText(text)
        self.live_label.setVisible(bool(text))

    # ---- Test lights: a guided test that asks what the rings show ----
    TEST_COLORS = [("Red", (255, 0, 0)), ("Green", (0, 255, 0)), ("Blue", (0, 0, 255))]
    TEST_ANSWERS = ["Red", "Green", "Blue", "White", "Left and right don't match", "Another color", "Dark / off"]
    SIDE_ANSWERS = ["Red", "Green", "Blue", "White", "Another color", "Dark / off"]

    # set while the one-time permission job runs, so the test starts by itself when it's done
    test_after_access = False

    def allow_access(self, *_args, then_test: bool = False):
        """One password prompt that covers the ring files and the lighting chip, saved for good."""
        # Always run the job: it rewrites the rules AND opens the files up immediately. Skipping it
        # because a rule file exists traps the owner in a restart loop when that file is stale.
        leds = self.leds or core.find_leds()
        self.test_after_access = then_test
        if not self.hub.enable_led_permissions(leds):
            self.test_after_access = False

    def access_job_done(self, ok: bool):
        """Called when the permission job finishes."""
        want_test, self.test_after_access = self.test_after_access, False
        self.refresh()
        if not ok:
            return
        leds = core.find_leds()
        if not core.lighting_access_ok(leds):
            self._report_access_problem(leds)
        elif want_test:
            QTimer.singleShot(500, lambda: self.test_lights(auto=True))

    def _report_access_problem(self, leds):
        """Permission was set up but still doesn't work: send exactly which file is blocked."""
        details = (f"Lighting permission didn't take\n\n{core.lighting_access_details(leds)}"
                   f"\n\nLEDs:\n{core.lighting_diagnostics()}")
        core.app_log("lighting", details.replace("\n", " | ")[:1500])
        sent = core.queue_report("lighting", "Lighting permission didn't take", details,
                                 core._fingerprint("light-access", core.VERSION))
        if sent and core.LAST_QUEUE == "queued":
            self.hub.send_reports_now()
        note = ("The details were sent automatically so this can be fixed."
                if sent and core.LAST_QUEUE == "queued" else core.report_hint())
        msg_info(self, APP_NAME, "Ally Hub set up the lighting permission, but your system "
                                                f"still blocks part of it. No need to restart.\n\n{note}")

    def test_lights(self, *_args, auto: bool = False):
        self.leds = core.find_leds()
        if not self.leds:
            self._test_failed("No ring lights found", [])
            return
        if not core.lighting_access_ok(self.leds):
            if ask(self, "Ally Hub needs a one-time permission to change the lights. You'll be asked for "
                         "your password once, and it's remembered after that.\n\nThe light test starts "
                         "by itself when it's done. Allow it now?"):
                self.allow_access(then_test=True)
            return
        if not auto and not ask(self, "Light test\n\nThe rings will show a few colors one at a time. After each one, "
                           "tap the color you actually see. It takes about a minute.\n\nStart?"):
            return
        self._start_light_test()

    def _start_light_test(self):
        self.btn_test.setEnabled(False)
        self._test_prev = (self.effect, self.brightness)
        # park the agent on a still color so it doesn't paint over the test colors
        update_config(lambda c: c["lighting"].__setitem__(
            "effect", core.normalize_effect({"type": "static", "colors": ["#000000"]})))
        QTimer.singleShot(1300, self._run_light_test)

    def _pick(self, text: str, answers: list):
        box = QMessageBox(self)
        box.setWindowTitle("Light test")
        box.setText(text)
        buttons = {box.addButton(a, QMessageBox.AcceptRole): a for a in answers}
        stop = box.addButton("Stop test", QMessageBox.RejectRole)
        run_dialog(box)
        clicked = box.clickedButton()
        if clicked is stop:
            return None
        return buttons.get(clicked)

    def _ask_color(self, label: str):
        saw = self._pick(f"{label}\n\nWhat color are the rings right now?", self.TEST_ANSWERS)
        if saw != "Left and right don't match":
            return saw
        # mixed rings are a big clue (some zones update, some don't), so record each side
        left = self._pick(f"{label}\n\nWhat color is the LEFT stick ring?", self.SIDE_ANSWERS)
        if left is None:
            return None
        right = self._pick(f"{label}\n\nWhat color is the RIGHT stick ring?", self.SIDE_ANSWERS)
        if right is None:
            return None
        return f"Mixed L={left} R={right}"

    def light_test_routes(self, leds: list) -> tuple:
        """[(route id, label)] to try in order, plus notes on sysfs methods skipped by readback.
        sysfs routes first (smooth software effects), then every direct-to-chip method."""
        routes, probes = [], []
        if core.has_packed_channels(leds):
            for enc in core.TEST_ENCODINGS:
                # probe with white: if the kernel changes the value (the 255 cap), skip it
                pr = core.write_test_color(leds, (255, 255, 255), enc)
                if pr.get("matches") is False:
                    probes.append(f"{enc}: kernel changed {pr['wrote']} to {pr['readback']}")
                else:
                    routes.append((enc, f"System lights ({enc})"))
        else:
            routes.append(("standard", "System lights"))
        if core.hid_available(leds):
            routes += [(f"hid:{m}", core.HID_METHODS[m]["name"]) for m in core.TEST_HID_METHODS]
        return routes, probes

    def _run_light_test(self):
        leds = core.find_leds() or self.leds
        # the agent must not touch the lights at all during the test: its writes make the kernel
        # driver re-send its own (blue) color over the chip packets
        paused = core.pause_agent()
        try:
            routes, probes = self.light_test_routes(leds)
            if not routes:
                self._finish_light_test([], None, False, note="sysfs changes every color and no lighting chip "
                                                              "interface was found. " + "; ".join(probes))
                return
            results, working, cancelled = [], None, False
            for i, (route, name) in enumerate(routes, 1):
                label = f"Method {i} of {len(routes)}: {name}"
                ok = True
                # red, green, blue: three right answers in a row prove a method (some get red
                # right, then stick). A wrong answer skips straight to the next method.
                core.hid_reset_session()
                for cname, rgb in self.TEST_COLORS:
                    res = (core.hid_test_color(leds, rgb, route[4:]) if route.startswith("hid:")
                           else core.write_test_color(leds, rgb, route))
                    QApplication.processEvents()
                    saw = self._ask_color(label)
                    if saw is None:
                        cancelled = True
                        break
                    res.update(encoding=route, expected=cname, saw=saw)
                    results.append(res)
                    if saw != cname:
                        ok = False
                        break
                if cancelled:
                    break
                if ok:
                    working = route
                    break
            self._finish_light_test(results, working, cancelled, note="; ".join(probes))
        finally:
            if paused:
                core.resume_agent()

    def _finish_light_test(self, results: list, working, cancelled: bool, note: str = ""):
        self.btn_test.setEnabled(True)
        if working and working.startswith("hid:"):
            update_config(lambda c: c["lighting"].update(encoding="hid", hid_method=working[4:]))
        elif working and working != "standard":
            update_config(lambda c: c["lighting"].__setitem__("encoding", working))
        if self._test_prev:
            self.effect, self.brightness = self._test_prev
            self._test_prev = None
            self.sync_editor()
            self.apply()
        if cancelled and not results:
            self.hub.toast("Light test stopped")
            return
        if note:
            table_note = f"note: {note}\n"
        else:
            table_note = ""
        table = "\n".join(
            f"{r['encoding']:<11} expected {r['expected']:<6} saw {r['saw']:<22} "
            f"wrote {r['wrote']} read back {r['readback']}" + (f" errors {r['errors']}" if r['errors'] else "")
            for r in results)
        outcome = (f"works with encoding '{working}'" if working else
                   "stopped early" if cancelled else "no encoding showed the right colors")
        title = f"Light test: {outcome}"
        nodes = core.ally_hid_nodes(core.find_leds())
        details = (f"{title}\n\n{table_note}{table}\nsysfs capped: {core.sysfs_color_capped(core.find_leds())}"
                   f"\nlighting chip: {nodes['lighting']} dynamic lighting: {nodes['dynamic']}"
                   f"\n\nagent: {core.agent_running()} "
                   f"state: {core.agent_state().get('led')}\n\nLEDs:\n{core.lighting_diagnostics()}")
        core.app_log("lighting", details.replace("\n", " | ")[:1500])
        # each guided test is its own report, so it's never skipped as a duplicate
        sent = core.queue_report("lighting", title, details, core._fingerprint("light-test", time.time()))
        if sent and core.LAST_QUEUE == "queued":
            self.hub.send_reports_now()
        note = ("The results were sent automatically." if sent and core.LAST_QUEUE == "queued"
                else core.report_hint())
        if working:
            extra = ("\n\nYour effects now run on the lighting chip itself. Animated ones use its built-in "
                     "pulse and rainbow modes, so Candle and Twinkle become a two-color pulse."
                     if working.startswith("hid:") else "")
            msg_info(self, APP_NAME, "Your rings work now. Ally Hub saved the setting "
                                                    f"that shows the right colors.{extra}\n\n{note}")
        else:
            msg_info(self, APP_NAME, "Thanks. None of the color settings looked right yet, "
                                                    f"so this needs a fix.\n\n{note}")

    def _test_failed(self, title: str, results: list):
        details = (f"{title}\nwrites ok: {results}\nagent: {core.agent_running()} "
                   f"state: {core.agent_state().get('led')}\n\nLEDs:\n{core.lighting_diagnostics()}")
        core.app_log("lighting", details.replace("\n", " | ")[:1500])
        sent = core.queue_report("lighting", title, details,
                                 core._fingerprint("lighting", title, core.VERSION))
        if sent and core.LAST_QUEUE == "queued":
            self.hub.toast("Sending the light details…")
            self.hub.send_reports_now()
        else:
            msg_info(self, APP_NAME, f"{title}.\n\n{core.report_hint()}\n\n"
                                    + core.lighting_diagnostics())


class LightingSection(QStackedWidget):
    """Customize → Lighting: the studio when Ally Hub drives the rings, the HueSync page otherwise."""

    def __init__(self, studio, huesync):
        super().__init__()
        self.studio, self.huesync = studio, huesync
        self.addWidget(studio)
        self.addWidget(huesync)
        self.show_current()

    def current(self):
        return self.huesync if core.lighting_shelved() else self.studio

    def show_current(self):
        self.setCurrentWidget(self.current())

    def refresh(self):
        self.show_current()
        self.current().refresh()


class HueSyncPage(QWidget):
    """Lighting is handled by the HueSync Decky plugin; this page installs and explains it."""

    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        v = page_shell(self, "Lighting", "Ring lights on the ROG Ally series are handled by HueSync, "
                                         "a Decky plugin built for this hardware.")
        card, cv = titled_card("lightbulb", "#a855f7", "HueSync",
                               "Colors, brightness, per-zone lighting and animated effects for the "
                               "ROG Ally, Ally X and Xbox Ally X, right from the Quick Access menu "
                               "in Game Mode.")
        self.status = label("", "statValue", wrap=True)
        cv.addWidget(self.status)
        row = QHBoxLayout()
        self.btn_install = button("Install HueSync", self.install, "primary")
        row.addWidget(self.btn_install)
        row.addWidget(button("Open the plugin store", lambda: hub.go("Plugin store")))
        row.addStretch()
        cv.addLayout(row)
        cv.addWidget(label("To use it: in Game Mode press the ••• (Quick Access) button, open the plug "
                           "icon, then HueSync.", "cardDesc", wrap=True))
        cv.addWidget(label("Ally Hub doesn't touch the ring lights, so the two never fight over them.",
                           "cardMeta", wrap=True))
        v.addWidget(card)
        own, ov = titled_card("sparkles", core.THEMES["ROG Crimson"]["accent"], "Or let Ally Hub drive the rings",
                              "Ally Hub's Lighting studio talks to the lighting chip the same way HueSync "
                              "does, and adds effects, battery rings, per-game colors and phone control.")
        orow = QHBoxLayout()
        orow.addWidget(button("Use Ally Hub lighting", hub.use_allyhub_lighting, "primary"))
        orow.addStretch()
        ov.addLayout(orow)
        v.addWidget(own)
        v.addStretch()

    def installed(self) -> bool:
        return any("huesync" in k for k in self.hub.state.get("decky", {}))

    def refresh(self):
        decky = CATALOG_BY_ID["decky"].check(self.hub.state)
        if self.installed():
            self.status.setText("✔ Installed")
            self.btn_install.setText("Reinstall / Update")
        elif not decky:
            self.status.setText("Needs Decky Loader first")
            self.btn_install.setText("Install Decky, then HueSync")
        else:
            self.status.setText("Not installed")
            self.btn_install.setText("Install HueSync")

    def install(self):
        if not CATALOG_BY_ID["decky"].check(self.hub.state):
            self.hub.on_item_action("decky", "install")
            self.hub.toast("Installing Decky first. Tap Install HueSync again when it's done.", 7000)
            return

        def go(plugins):
            p = next((p for p in plugins if (p.get("name") or "").lower() == "huesync"), None)
            if p:
                self.hub.on_store_action(p, "install")
            else:
                self.hub.toast("Couldn't find HueSync in the plugin store right now. Try again later.", 7000)
        self.hub.store_page.with_plugins(go)
        self.hub.toast("Getting HueSync from the plugin store…")


# ==========================================================================
# Automation (agent features)
# ==========================================================================

class AutomationPage(QWidget):
    """Not a page since 1.4.0: builds the background helper card and switches (Settings > General), the
    automatic lighting block (Customize > Lighting, Ally Hub lighting only) and scheduled save backups
    (Games > Saves), and keeps their logic."""

    GENERAL = [
        ("guardian", "Update Guardian",
         "Watches for SteamOS updates and a missing Decky, and backs up your settings daily."),
        ("health_log", "Battery history", "Records battery, power draw and temperatures for Home."),
        ("dock_mode", "Dock mode", "When you plug into a TV or monitor, switch lighting and audio."),
    ]
    LIGHTS = [
        ("battery_rings", "Battery rings",
         "Rings fade from green to red as your battery drains, and breathe while charging."),
        ("low_battery_flash", "Low battery flash", "Rings flash red at 15% or lower."),
        ("game_colors", "Per-game lighting", "Rings switch to the color or effect you pick for each game."),
    ]
    FEATURES = GENERAL + LIGHTS

    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self.game_previews = []
        self._anim = QTimer(self)          # animates the per-game previews while they're on screen
        self._anim.timeout.connect(self._tick_previews)     # started by Hub.on_page_shown on Lighting
        card, cv = titled_card("bot", core.THEMES["ROG Crimson"]["accent"], "Background helper",
                               "Runs quietly in the background, in Game Mode too: lighting, Game Boost, save "
                               "snapshots, the Quick Access panel and the phone remote need it.")
        self.agent_status = label("", "cardDesc", wrap=True)
        cv.addWidget(self.agent_status)
        row = QHBoxLayout()
        self.btn_agent = button("", self.toggle_agent)
        row.addWidget(self.btn_agent)
        row.addStretch()
        cv.addLayout(row)
        self.checks = {}

        def switches(features):
            grid = two_col_grid()
            for n, (key, title, desc) in enumerate(features):
                c = card_frame()
                cl = QVBoxLayout(c)
                cl.setContentsMargins(20, 16, 20, 16)
                cb = QCheckBox(title)
                cb.toggled.connect(lambda on, k=key: self.set_feature(k, on))
                cl.addWidget(cb)
                cl.addWidget(label(desc, "cardDesc", wrap=True))
                if key == "dock_mode":
                    self.dock_audio = QCheckBox("Switch audio to the TV or monitor")
                    self.dock_audio.toggled.connect(
                        lambda on: update_config(lambda c: c["dock"].__setitem__("audio_hdmi", on)))
                    cl.addWidget(self.dock_audio)
                self.checks[key] = cb
                grid.addWidget(c, n // 2, n % 2)
            return grid
        self.block_general = block(card, switches(self.GENERAL))

        gcard = card_frame()
        gv = QVBoxLayout(gcard)
        gv.setContentsMargins(20, 18, 20, 18)
        gv.addWidget(label("Per-game colors", "cardTitle"))
        self.now_playing = label("", "cardDesc", wrap=True)
        gv.addWidget(self.now_playing)
        self.games_box = QVBoxLayout()
        self.games_box.setSpacing(8)
        gv.addLayout(self.games_box)
        dcard = card_frame()
        dv = QHBoxLayout(dcard)
        dv.setContentsMargins(20, 18, 20, 18)
        dv.addWidget(label("Lights when docked:", "cardDesc"))
        self.dock_lights = QComboBox()
        self.dock_lights.addItems(["Turn off", "Keep my color", "Custom color…"])
        self.dock_lights.activated.connect(self.set_dock_lights)
        self.dock_lights.setProperty("padCycle", False)   # its last option opens a color picker
        dv.addWidget(self.dock_lights)
        dv.addStretch()
        self.block_lighting = block(switches(self.LIGHTS), gcard, dcard, heading="Automatic lighting")

        scard, sv = titled_card("save", "#0891b2", "Scheduled backups",
                                "Backs up every game's saves (Steam, Heroic, Lutris and emulators) on a schedule. "
                                "Runs only when no game is playing and the battery is above 30%.")
        self.save_enable = QCheckBox("Back up automatically")
        self.save_enable.toggled.connect(lambda on: self.set_feature("save_backup", on))
        sv.addWidget(self.save_enable)
        r = QHBoxLayout()
        r.addWidget(label("Every", "cardDesc"))
        self.save_every = QComboBox()
        self.intervals = [(6, "6 hours"), (12, "12 hours"), (24, "day"), (72, "3 days"), (168, "week")]
        self.save_every.addItems([t for _, t in self.intervals])
        self.save_every.activated.connect(lambda i: update_config(
            lambda c: c["agent"].__setitem__("save_backup_hours", self.intervals[i][0])))
        r.addWidget(self.save_every)
        r.addWidget(adv(button("Choose folder…", self.choose_save_dir)))
        self.btn_save_now = button("Back up now", self.backup_now, "primary")
        r.addWidget(self.btn_save_now)
        r.addStretch()
        sv.addLayout(r)
        self.save_info = label("", "cardMeta", wrap=True)
        sv.addWidget(self.save_info)
        self.block_saves = scard

    def _tick_previews(self):
        for w in self.game_previews:
            try:
                if w.isVisible():
                    w.update()
            except RuntimeError:          # its row was rebuilt
                pass

    def refresh(self):
        cfg = load_config()
        a = cfg["agent"]
        running = core.agent_running()
        st = core.agent_state()
        if running:
            extra = f" Lighting: {st.get('led')}." if st.get("led") else ""
            self.agent_status.setText("✔ Running." + extra)
            self.btn_agent.setText("Turn it off")
            self.btn_agent.setObjectName("danger")
        else:
            self.agent_status.setText("Off. Turn it on for the switches below "
                                      "(they keep working after reboots and in Game Mode).")
            self.btn_agent.setText("Turn it on")
            self.btn_agent.setObjectName("primary")
        repolish(self.btn_agent)
        for key, cb in self.checks.items():
            cb.blockSignals(True)
            cb.setChecked(bool(a.get(key)))
            cb.blockSignals(False)
        self.save_enable.blockSignals(True)
        self.save_enable.setChecked(bool(a.get("save_backup")))
        self.save_enable.blockSignals(False)
        hours = a.get("save_backup_hours", 24)
        idx = next((i for i, (h, _) in enumerate(self.intervals) if h == hours), 2)
        self.save_every.setCurrentIndex(idx)
        last = (core.read_json(core.DATA_DIR / "save_backup.json", {}) or {}).get("last")
        lud = core.LUDUSAVI_ID in self.hub.state["flatpaks"]
        self.save_info.setText(
            f"Folder: {a.get('save_backup_dir')} · Last backup: "
            f"{time.strftime('%b %d %H:%M', time.localtime(last)) if last else 'never'}"
            + ("" if lud else " · Needs Ludusavi (Store, or the button above)"))
        self.btn_save_now.setEnabled(lud)
        lights = cfg["dock"].get("lights", "off")
        self.dock_lights.setCurrentIndex(0 if lights == "off" else 1 if lights == "keep" else 2)
        self.dock_audio.blockSignals(True)
        self.dock_audio.setChecked(bool(cfg["dock"].get("audio_hdmi")))
        self.dock_audio.blockSignals(False)
        self.refresh_games(cfg, st)

    def refresh_games(self, cfg, st):
        self.game_previews = []
        clear_layout(self.games_box)
        seen = core.read_json(core.DATA_DIR / "seen_games.json", {}) or {}
        current = st.get("game")
        self.now_playing.setText(
            f"Now playing: {st.get('game_name') or current}" if current
            else "Games you play show up here once the background helper sees them. Pick a color for each.")
        colors = cfg.get("game_colors", {})
        order = sorted(seen.items(), key=lambda kv: (kv[0] != current, kv[1].lower()))
        for appid, name in order[:30]:
            row = QHBoxLayout()
            ref = colors.get(appid)
            eff = core.lookup_effect(ref, cfg) if ref else None
            if eff:
                sw = RingPreview(64, 28)
                sw.set_effect(eff)
                self.game_previews.append(sw)
            else:
                sw = QLabel()
                sw.setFixedSize(64, 28)
                sw.setStyleSheet("border-radius: 14px; border: 2px dashed #5d6478;")
            row.addWidget(sw)
            row.addWidget(label(("▶ " if appid == current else "") + name, "cardDesc"), 1)
            if eff:
                row.addWidget(label(core.effect_label(eff), "cardMeta"))
            row.addWidget(button("Color", lambda _=False, a=appid: self.pick_game_color(a)))
            row.addWidget(button("Effect", lambda _=False, a=appid: self.pick_game_effect(a)))
            col = ref
            if col:
                row.addWidget(button("Clear", lambda _=False, a=appid: self.clear_game_color(a)))
            self.games_box.addLayout(row)

    def set_feature(self, key, on):
        update_config(lambda c: c["agent"].__setitem__(key, on))
        if on and not core.agent_running():          # one rule everywhere: start it and say so
            self.hub.enable_agent()
            self.hub.toast("Saved. The background helper is on now.")
            return
        self.hub.toast("Saved")

    def toggle_agent(self):
        if core.agent_running():
            self.hub.disable_agent()
        else:
            self.hub.enable_agent()

    def pick_game_effect(self, appid):
        names = list(core.PRESETS) + list(load_config()["lighting"].get("custom") or {})
        name, ok = ask_item(self, "Effect for this game", "Effect:", names)
        if ok and name:
            update_config(lambda cfg: cfg["game_colors"].__setitem__(appid, "preset:" + name))
            self.refresh()

    def pick_game_color(self, appid):
        cur = load_config()["game_colors"].get(appid, "#e11d48")
        cur = cur if cur.startswith("#") else "#e11d48"
        c = ask_color(QColor(cur), self, "Color for this game")
        if c.isValid():
            update_config(lambda cfg: cfg["game_colors"].__setitem__(appid, c.name()))
            self.refresh()

    def clear_game_color(self, appid):
        update_config(lambda cfg: cfg["game_colors"].pop(appid, None))
        self.refresh()

    def set_dock_lights(self, idx):
        if idx == 0:
            val = "off"
        elif idx == 1:
            val = "keep"
        else:
            c = ask_color(QColor("#ffffff"), self, "Docked lighting color")
            if not c.isValid():
                self.refresh()
                return
            val = c.name()
        update_config(lambda cfg: cfg["dock"].__setitem__("lights", val))

    def choose_save_dir(self):
        cur = load_config()["agent"].get("save_backup_dir")
        d = QFileDialog.getExistingDirectory(self.hub, "Where should save backups go?", cur or str(HOME),
                                             options=QFileDialog.ShowDirsOnly | file_dialog_options())
        if d:
            update_config(lambda c: c["agent"].__setitem__("save_backup_dir", d))
            self.refresh()

    def backup_now(self):
        d = load_config()["agent"].get("save_backup_dir") or str(core.BACKUP_DIR / "saves")
        stamp_file = shlex.quote(str(core.DATA_DIR / "save_backup.json"))
        cmd = (f"mkdir -p {shlex.quote(d)} && flatpak run {core.LUDUSAVI_ID} backup --force "
               f"--path {shlex.quote(d)} && "
               f"echo '{{\"last\": '$(date +%s)', \"rc\": 0}}' > {stamp_file}")
        self.hub.runner.submit("Back up game saves", cmd, "saves")


# ==========================================================================
# Connect (Wake my PC, Tailscale, phone remote)
# ==========================================================================

class ConnectPage(QWidget):
    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        v = page_shell(self, "Connect", "Wake your PC, stream from anywhere, and control your Ally "
                                        "from your phone.")
        grid = two_col_grid()

        wcard, wv = titled_card("power", "#22c55e", "Wake my PC",
                                "Boot your gaming PC remotely before you open Moonlight. Turn on "
                                "Wake-on-LAN in the PC's BIOS and network adapter settings.")
        self.wol_name = QLineEdit()
        self.wol_name.setPlaceholderText("Name (e.g. Gaming PC)")
        self.wol_mac = QLineEdit()
        self.wol_mac.setPlaceholderText("MAC address, e.g. 1C:2B:3A:4D:5E:6F")
        wv.addWidget(self.wol_name)
        wv.addWidget(self.wol_mac)
        wr = QHBoxLayout()
        wr.addWidget(button("Save", self.save_wol))
        self.btn_wake = button("Wake now", self.wake, "primary")
        wr.addWidget(self.btn_wake)
        self.btn_moon = button("Open Moonlight", self.open_moonlight)
        wr.addWidget(self.btn_moon)
        wr.addStretch()
        wv.addLayout(wr)
        wv.addWidget(label("Find the MAC on your PC with: ipconfig /all (Windows) or ip link (Linux).",
                           "cardMeta", wrap=True))
        wv.addStretch()
        grid.addWidget(wcard, 0, 0)

        tcard, tv = titled_card("globe", "#64748b", "Play from anywhere (Tailscale)",
                                "Puts your Ally and PC on a private network so Moonlight works over "
                                "cellular or hotel Wi-Fi. Install Tailscale on your PC too.")
        self.ts_status = label("", "cardDesc", wrap=True)
        tv.addWidget(self.ts_status)
        tr = QHBoxLayout()
        self.btn_ts_install = button("Install", lambda: hub.on_item_action("tailscale", "install"), "primary")
        self.btn_ts_login = button("Log in", self.ts_login, "primary")
        self.btn_ts_logout = button("Log out", self.ts_logout)
        for b in (self.btn_ts_install, self.btn_ts_login, self.btn_ts_logout):
            tr.addWidget(b)
        tr.addStretch()
        tv.addLayout(tr)
        tv.addStretch()
        grid.addWidget(tcard, 0, 1)
        v.addLayout(grid)

        rcard, rv = titled_card("smartphone", "#a855f7", "Phone remote",
                                "Open a page on your phone to check battery and temps, change ring "
                                "colors, set game colors and wake your PC. Works on your home Wi-Fi "
                                "(and anywhere via Tailscale). Protected by a PIN.")
        self.remote_enable = QCheckBox("Enable phone remote")
        self.remote_enable.toggled.connect(self.toggle_remote)
        rv.addWidget(self.remote_enable)
        rr = QHBoxLayout()
        rr.addWidget(label("Port", "cardDesc"))
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.editingFinished.connect(
            lambda: update_config(lambda c: c["agent"].__setitem__("remote_port", self.port.value())))
        rr.addWidget(self.port)
        rr.addWidget(button("New PIN", self.new_pin))
        rr.addStretch()
        rv.addLayout(rr)
        self.remote_info = label("", "statValue", wrap=True)
        self.remote_info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rv.addWidget(self.remote_info)
        v.addWidget(rcard)
        v.addStretch()

    def refresh(self):
        cfg = load_config()
        w = cfg["wol"]
        self.wol_name.setText(w.get("name", ""))
        self.wol_mac.setText(w.get("mac", ""))
        self.btn_wake.setEnabled(bool(core.normalize_mac(w.get("mac", ""))))
        self.btn_moon.setVisible("com.moonlight_stream.Moonlight" in self.hub.state["flatpaks"])

        installed = Path(core.TAILSCALE_BIN).exists()
        self.btn_ts_install.setVisible(not installed)
        ip = ""
        if installed:
            rc, out = core.run_quiet([core.TAILSCALE_BIN, "ip", "-4"], timeout=4)
            ip = out.splitlines()[0] if rc == 0 and out else ""
        self.btn_ts_login.setVisible(installed and not ip)
        self.btn_ts_logout.setVisible(installed and bool(ip))
        self.ts_status.setText(
            "Not installed." if not installed else
            f"✔ Connected. This Ally's Tailscale address: {ip}" if ip else
            "Installed but not logged in. Tap Log in, then follow the link in the Activity log.")

        a = cfg["agent"]
        self.remote_enable.blockSignals(True)
        self.remote_enable.setChecked(bool(a.get("remote")))
        self.remote_enable.blockSignals(False)
        self.port.setValue(int(a.get("remote_port") or 8787))
        if a.get("remote") and a.get("remote_pin"):
            ips = core.local_ips() or ["<your Ally's IP>"]
            urls = "\n".join(f"http://{ip}:{a['remote_port']}" for ip in ips)
            running = core.agent_running()
            self.remote_info.setText(
                f"On your phone, open:\n{urls}\nPIN: {a['remote_pin']}"
                + ("" if running else "\n(The background helper is off: turn it on in Settings → General)"))
        else:
            self.remote_info.setText("")

    def save_wol(self):
        mac = self.wol_mac.text().strip()
        if mac and not core.normalize_mac(mac):
            msg_warn(self, APP_NAME, "That MAC address doesn't look right.")
            return
        name = self.wol_name.text().strip() or "Gaming PC"
        update_config(lambda c: c["wol"].update(name=name, mac=mac))
        self.hub.toast("Saved")
        self.refresh()

    def wake(self):
        w = load_config()["wol"]
        ok = core.send_wol(w.get("mac", ""), w.get("broadcast", ""))
        self.hub.toast(f"Wake signal sent to {w.get('name')}" if ok else "Couldn't send the wake signal")

    def open_moonlight(self):
        self.hub.launch("flatpak run com.moonlight_stream.Moonlight")

    def ts_login(self):
        if self.hub.needs_password():
            return
        self.hub.runner.submit(
            "Tailscale login",
            f"echo 'Open the link below on your phone to log in:'; "
            f"sudo {core.TAILSCALE_BIN} up --operator=\"$USER\" --qr", "tailscale-login")
        self.hub.go("Activity")

    def ts_logout(self):
        self.hub.runner.submit("Tailscale logout", f"sudo {core.TAILSCALE_BIN} logout", "tailscale-logout")

    def toggle_remote(self, on):
        def fn(c):
            c["agent"]["remote"] = on
            if on and not c["agent"].get("remote_pin"):
                c["agent"]["remote_pin"] = f"{secrets.randbelow(10**6):06d}"
        update_config(fn)
        if on and not core.agent_running():
            self.hub.enable_agent()
        QTimer.singleShot(1500, self.refresh)

    def new_pin(self):
        update_config(lambda c: c["agent"].__setitem__("remote_pin", f"{secrets.randbelow(10**6):06d}"))
        self.refresh()


# ==========================================================================
# Health dashboard
# ==========================================================================

class LineChart(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(260)
        self.points = []
        self.unit = ""
        self.color = QColor("#e11d48")
        self.text = QColor("#e7e9f0")
        self.grid = QColor("#2e3448")
        self.span = 86400

    def set_data(self, points, unit, color, text, grid, span):
        self.points, self.unit, self.span = points, unit, span
        self.color, self.text, self.grid = QColor(color), QColor(text), QColor(grid)
        self.update()

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(48, 14, -14, -28)
        f = p.font()
        f.setPointSize(9)
        p.setFont(f)
        if len(self.points) < 2:
            p.setPen(self.text)
            p.drawText(self.rect(), Qt.AlignCenter, "Not enough data yet")
            return
        vals = [v for _, v in self.points]
        lo, hi = min(vals), max(vals)
        if hi - lo < 1:
            lo, hi = lo - 1, hi + 1
        pad = (hi - lo) * 0.1
        lo, hi = lo - pad, hi + pad
        t1 = time.time()
        t0 = t1 - self.span
        p.setPen(QPen(self.grid, 1))
        for i in range(5):
            y = r.top() + r.height() * i / 4
            p.drawLine(r.left(), int(y), r.right(), int(y))
            p.setPen(self.text)
            p.drawText(QRectF(0, y - 9, 44, 18), Qt.AlignRight | Qt.AlignVCenter,
                       f"{hi - (hi - lo) * i / 4:.0f}{self.unit}")
            p.setPen(QPen(self.grid, 1))
        p.setPen(self.text)
        for i in range(5):
            t = t0 + self.span * i / 4
            x = r.left() + r.width() * i / 4
            fmt = "%a %H:%M" if self.span > 86400 else "%H:%M:%S" if self.span <= 120 else "%H:%M"
            p.drawText(QRectF(x - 50, r.bottom() + 6, 100, 18), Qt.AlignCenter,
                       time.strftime(fmt, time.localtime(t)))

        def xy(t, v):
            return QPointF(r.left() + r.width() * (t - t0) / self.span,
                           r.bottom() - r.height() * (v - lo) / (hi - lo))
        path = QPainterPath()
        last_t = None
        for t, v in self.points:
            pt = xy(t, v)
            if last_t is None or t - last_t > 300:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
            last_t = t
        p.setPen(QPen(self.color, 2.5))
        p.drawPath(path)


class HealthPage(QWidget):
    SERIES = [("pct", "Battery", "%"), ("w", "Power draw", "W"), ("cpu", "CPU temp", "°"),
              ("gpu", "GPU temp", "°")]
    RANGES = [(60, "1 minute"), (3600, "1 hour"), (12 * 3600, "12 hours")]
    SAMPLE_MS = 2000      # the app's own readings, so the 1-minute view has detail (the agent logs once a minute)

    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        v = page_shell(self, "Health", "Live readings, history and which games drain your battery.")
        # Home notices: only shown when something needs you (setup left, no password, Decky gone after an update)
        self.setup_card = QFrame()
        self.setup_card.setObjectName("banner")
        scl = QVBoxLayout(self.setup_card)
        scl.setContentsMargins(20, 14, 20, 14)
        scl.addWidget(label("Finish setting up", "cardTitle"))
        self.setup_items = QVBoxLayout()
        scl.addLayout(self.setup_items)
        sr = QHBoxLayout()
        sr.addWidget(button("Open setup", lambda: hub.go("Setup"), "primary"))
        sr.addWidget(button("Hide", self.hide_setup))
        sr.addStretch()
        scl.addLayout(sr)
        self.setup_card.hide()
        v.addWidget(self.setup_card)
        self.alerts_box = QVBoxLayout()
        self.alerts_box.setSpacing(8)
        v.addLayout(self.alerts_box)
        self.pw_banner = QFrame()
        self.pw_banner.setObjectName("banner")
        pl = QHBoxLayout(self.pw_banner)
        pl.setContentsMargins(20, 14, 20, 14)
        pl.addWidget(label("Set a sudo password so Ally Hub can install mods and plugins.",
                           "bannerText", wrap=True), 1)
        pl.addWidget(button("Set password", hub.set_password, "primary"))
        self.pw_banner.hide()
        v.addWidget(self.pw_banner)
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(20, 12, 20, 12)
        bl.addWidget(label("History needs the background helper with Battery history on.", "bannerText", wrap=True), 1)
        bl.addWidget(button("Set up", lambda: hub.go("General"), "primary"))
        v.addWidget(self.banner)
        grid = QGridLayout()
        grid.setSpacing(16)
        self.live = {k: StatTile(k, big=True) for k in
                     ("Battery", "Time left", "Power draw", "CPU", "GPU", "Fan")}
        for n, t in enumerate(self.live.values()):
            grid.addWidget(t, n // 3, n % 3)
        v.addLayout(grid)
        self.slot = v.count()          # the Checkup and Quick fixes go here (Hub puts them in)
        v.addWidget(label("HISTORY", "section"))
        chips = QHBoxLayout()
        self.series_chips, self.range_chips = {}, {}
        for key, name, _u in self.SERIES:
            c = button(name, lambda _=False, k=key: self.set_series(k), "chip")
            c.setCheckable(True)
            self.series_chips[key] = c
            chips.addWidget(c)
        chips.addSpacing(20)
        for span, name in self.RANGES:
            c = button(name, lambda _=False, s=span: self.set_range(s), "chip")
            c.setCheckable(True)
            self.range_chips[span] = c
            chips.addWidget(c)
        chips.addStretch()
        v.addLayout(chips)
        chart_card = card_frame()
        cl = QVBoxLayout(chart_card)
        cl.setContentsMargins(12, 12, 12, 12)
        self.chart = LineChart()
        cl.addWidget(self.chart)
        v.addWidget(chart_card)
        v.addWidget(label("BATTERY DRAIN BY GAME", "section"))
        self.games_card = card_frame()
        self.games_box = QVBoxLayout(self.games_card)
        self.games_box.setContentsMargins(20, 16, 20, 16)
        v.addWidget(self.games_card)
        v.addStretch()
        self.info = label("", "footInfo", wrap=True)
        v.addWidget(self.info, 0, Qt.AlignRight)
        self.series, self.span = "pct", 3600
        self.recent = collections.deque(maxlen=150)    # about 5 minutes of 2-second readings
        self.sampler = QTimer(self)                    # runs while the app is open, even off this page
        self.sampler.timeout.connect(self.sample)
        self.sampler.start(self.SAMPLE_MS)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)

    def refresh_notices(self, state: dict):
        osr = core.os_release()
        self.info.setText(f"{core.device_name()} · SteamOS {osr.get('VERSION_ID', '?')} · "
                          f"Ally Hub {core.version_label()}")
        left = [t for _k, t, done in core.setup_checklist(state) if not done]
        hidden = (load_config().get("setup") or {}).get("checklist_hidden")
        clear_layout(self.setup_items)
        for t in left:
            self.setup_items.addWidget(label("○  " + t, "bannerText"))
        self.setup_card.setVisible(bool(left) and not hidden)
        self.pw_banner.hide()           # the Checkup lists a missing password with its fix (one place, 1.4.0)
        clear_layout(self.alerts_box)
        for a in core.read_json(core.DATA_DIR / "alerts.json", []) or []:
            f = QFrame()
            f.setObjectName("banner")
            h = QHBoxLayout(f)
            h.setContentsMargins(20, 12, 20, 12)
            h.addWidget(label(a.get("text", ""), "bannerText", wrap=True), 1)
            if a.get("id", "").startswith("decky-missing"):
                h.addWidget(button("Repair Decky",
                                   lambda: self.hub.on_item_action("decky", "install"), "primary"))
            h.addWidget(button("Dismiss", lambda _=False, i=a.get("id"): self.hub.dismiss_alert(i)))
            self.alerts_box.addWidget(f)

    def hide_setup(self, *_args):
        update_config(lambda c: c.setdefault("setup", {}).__setitem__("checklist_hidden", True))
        self.setup_card.hide()
        self.hub.toast("Hidden. Settings → General → Run setup again brings it back.")

    def sample(self):
        try:
            self.recent.append(core.health_now())
        except Exception:
            pass

    def tick(self):
        self.refresh_live()
        if self.span <= 120:
            self.refresh_chart()        # the 1-minute chart moves live

    def showEvent(self, ev):
        super().showEvent(ev)
        self.refresh()
        self.timer.start(2000)

    def hideEvent(self, ev):
        super().hideEvent(ev)
        self.timer.stop()

    def set_series(self, k):
        self.series = k
        self.refresh_chart()

    def set_range(self, s):
        self.span = s
        self.refresh_chart()

    def refresh(self):
        a = load_config()["agent"]
        self.banner.setVisible(not (core.agent_running() and a.get("health_log")))
        self.refresh_live()
        self.refresh_chart()
        self.refresh_games()

    def refresh_live(self):
        s = core.sensors()
        w = core.battery_power_w()
        self.live["Battery"].value.setText(core.battery_percent())
        self.live["Time left"].value.setText(core.time_left_text())
        self.live["Power draw"].value.setText(f"{w:.1f} W" if w else "n/a")
        self.live["CPU"].value.setText(f"{s['cpu_temp']:.0f}°C" if s["cpu_temp"] else "n/a")
        self.live["GPU"].value.setText(f"{s['gpu_temp']:.0f}°C" if s["gpu_temp"] else "n/a")
        self.live["Fan"].value.setText(f"{s['fan_rpm']} rpm" if s["fan_rpm"] is not None else "n/a")

    def refresh_chart(self):
        for k, c in self.series_chips.items():
            c.setChecked(k == self.series)
        for k, c in self.range_chips.items():
            c.setChecked(k == self.span)
        since = time.time() - self.span
        rows = [] if self.span <= 120 else core.read_health(since)
        rows += [r for r in self.recent if r["t"] >= since]
        pts = sorted((r["t"], r[self.series]) for r in rows if r.get(self.series) is not None)
        unit = next(u for k, _n, u in self.SERIES if k == self.series)
        pal = core.theme_palette(load_config()["theme"])
        self.chart.set_data(pts, unit, pal["accent"], pal["muted"], pal["border"], self.span)

    def refresh_games(self):
        clear_layout(self.games_box)
        rows = core.read_health(time.time() - 7 * 86400)
        drain = core.per_game_drain(rows)
        seen = core.read_json(core.DATA_DIR / "seen_games.json", {}) or {}
        _now, full = core.battery_energy_wh()
        if not drain:
            self.games_box.addWidget(label("Play a few games on battery with the background helper on and "
                                           "they'll show up here.", "cardDesc", wrap=True))
            return
        for appid, watts, samples in drain[:12]:
            r = QHBoxLayout()
            r.addWidget(label(seen.get(appid, appid), "cardTitle"), 1)
            r.addWidget(label(f"{watts:.1f} W avg", "cardDesc"))
            if full:
                r.addSpacing(16)
                r.addWidget(label(f"≈ {full / watts:.1f} h on a full charge", "statValue"))
            r.addSpacing(16)
            r.addWidget(label(f"{samples} min logged", "cardMeta"))
            self.games_box.addLayout(r)


# ==========================================================================
# Ally Doctor
# ==========================================================================

# ==========================================================================
# Launchers: NonSteamLaunchers in Ally Hub's own theme, controller friendly
# ==========================================================================

# Library art: core draws each picture as SVG, Qt turns it into a PNG here.
ART_GLYPHS = {"Game stores": ("store", "#3b82f6"), "Cloud gaming": ("cloud", "#16a34a"),
              "TV and video": ("tv", "#e11d48")}


def image_png(img) -> bytes:
    """A QImage as PNG bytes (empty when Qt couldn't make it)."""
    if img is None or img.isNull():
        return b""
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba.data())


def rasterize_svg(svg: str, w: int, h: int) -> bytes:
    """Render an SVG at w x h as PNG bytes, through the same SVG image plugin the icons use."""
    img = QImage()
    if not img.loadFromData(svg.encode(), "SVG") or img.isNull():
        return b""
    if img.width() != w or img.height() != h:
        img = img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return image_png(img.convertToFormat(QImage.Format_ARGB32))


def cover_png(path: str, w: int, h: int) -> bytes:
    """A picture of the owner's own, scaled to fill w x h and cropped in the middle."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)                 # phone photos: follow their rotation tag
    img = reader.read()
    if img.isNull():
        return b""
    img = img.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    return image_png(img.copy(max(0, (img.width() - w) // 2), max(0, (img.height() - h) // 2), w, h))


def art_glyph(name: str) -> tuple:
    """(Lucide icon body, color) for a tile without an icon of its own."""
    group = next((g for g, items in core.NSL_GROUPS.items() if any(n == name for n, _ in items)), "")
    icon, color = ART_GLYPHS.get(group, ("gamepad-2", "#8b5cf6"))
    return ICONS.get(icon, ""), color


def self_icon_png() -> bytes:
    svg = core.read_text(core.APP_DIR / "allyhub.svg")
    return rasterize_svg(svg.replace('viewBox="0 0 256 256"', 'width="512" height="512" viewBox="0 0 256 256"', 1),
                         512, 512) if svg else b""


def make_art(t: dict) -> tuple:
    """(pngs by kind, icon png) for one tile planned by core.art_plan."""
    icon, color = t.get("icon_png"), t.get("color")
    if t.get("self"):
        icon, color = self_icon_png() or None, "#e11d48"
    glyph, glyph_color = art_glyph(t["name"])
    svgs = core.art_svgs(t["name"], icon, color or (None if icon else glyph_color), glyph)
    pngs = {k: rasterize_svg(svg, w, h) for k, (svg, w, h) in svgs.items()}
    icon = icon or pngs.get("icon") or None
    return {k: v for k, v in pngs.items() if v and k != "icon"}, (None if t.get("has_icon") else icon)


class LaunchersPage(QWidget):
    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self.last_run = []
        self.removing = []
        v = page_shell(self, "Launchers",
                       "Add stores, cloud gaming and TV apps to your Steam library, ready in Game Mode, or remove "
                       "them again. Powered by NonSteamLaunchers.")
        self.checks = {}
        for group, items in core.NSL_GROUPS.items():
            v.addWidget(label(group.upper(), "section"))
            card = card_frame()
            grid = QGridLayout(card)
            grid.setContentsMargins(20, 16, 20, 16)
            grid.setHorizontalSpacing(24)
            grid.setVerticalSpacing(12)
            for n, (name, _rel) in enumerate(items):
                cb = QCheckBox(name)
                cb.toggled.connect(self.update_button)
                self.checks[name] = cb
                grid.addWidget(cb, n // 3, n % 3)
            v.addWidget(card)
        opts = card_frame()
        ov = QVBoxLayout(opts)
        ov.setContentsMargins(20, 16, 20, 16)
        self.separate = QCheckBox("Give each launcher its own Proton prefix")
        ov.addWidget(self.separate)
        ov.addWidget(label("Off is simpler and uses less space. Turn it on if one launcher keeps breaking another.",
                           "cardDesc", wrap=True))
        v.addWidget(opts)
        row = QHBoxLayout()
        self.btn_add = button("Add to Steam", self.add, "primary")
        self.btn_hide = button("Hide from Steam", self.hide)
        self.btn_remove = button("Uninstall", self.uninstall, "danger")
        row.addWidget(self.btn_add)
        row.addWidget(self.btn_hide)
        row.addWidget(self.btn_remove)
        row.addWidget(button("Clear", self.clear))
        row.addStretch()
        v.addLayout(row)
        self.status = label("", "cardMeta", wrap=True)
        v.addWidget(self.status)

        v.addWidget(label("LIBRARY ART", "section"))
        ac, av = titled_card("images", "#8b5cf6", "Library art",
                             "Blank blue tiles get a cover, banner and icon made right here on your handheld from "
                             "each program's own icon. Nothing is downloaded. New launchers get theirs "
                             "automatically.")
        arow = QHBoxLayout()
        self.btn_art = button("Fix artwork", self.fix_artwork, "primary")
        arow.addWidget(self.btn_art)
        arow.addWidget(button("Use my own picture", self.own_picture))
        arow.addStretch()
        av.addLayout(arow)
        v.addWidget(ac)

        v.addWidget(label("CLEAN UP", "section"))
        cc, cv = titled_card("trash", "#ef4444", "Leftover data",
                             "Finds what removed launchers left behind: old Proton prefixes, installer downloads, "
                             "the game scanner once nothing uses it, and old shortcut backups. You pick what goes.")
        crow = QHBoxLayout()
        self.btn_clean = button("Find leftovers", self.find_leftovers)
        crow.addWidget(self.btn_clean)
        crow.addStretch()
        cv.addLayout(crow)
        v.addWidget(cc)
        v.addStretch()
        self.update_button()

    def picked(self) -> list:
        return [n for n, cb in self.checks.items() if cb.isChecked()]

    def update_button(self, *_):
        names = self.picked()
        n = len(names)
        self.btn_add.setText(f"Add {n} to Steam" if n else "Add to Steam")
        self.btn_add.setEnabled(bool(n))
        self.btn_remove.setText(f"Uninstall {n}" if n else "Uninstall")
        self.btn_remove.setEnabled(bool(n))
        self.btn_hide.setEnabled(bool(n))

    def clear(self):
        for cb in self.checks.values():
            cb.setChecked(False)

    def refresh(self):
        have = [n for n in core.NSL_NAMES if core.nsl_installed(n)]
        for name, cb in self.checks.items():
            cb.setText(f"{name}  ✔" if name in have else name)
        self.status.setText(("Installed: " + ", ".join(sorted(have)) + ". Pick one and tap Add to repair it, or "
                             "Uninstall to remove it.") if have else
                            "Takes a few minutes per store. Progress shows in the activity log (Settings).")

    # ---- hide / show (the launcher stays installed) ----
    def hide(self, *_args):
        names = self.picked()
        if not names or not ask(self, "Take these out of your Steam library?\n\n" + "\n".join(f"• {n}" for n in names) +
                                "\n\nThey stay installed. Pick them and tap Add to Steam to bring the tiles back."):
            return
        self.clear()

        def done(removed):
            if removed is None:
                msg_warn(self, APP_NAME, "Steam's connection for plugins is off (it comes with Decky Loader), so the "
                                         "tiles couldn't be removed from here.")
            else:
                self.hub.toast(f"Hidden from Steam: {', '.join(removed) or 'nothing to hide'}")
        BackgroundTask(self, lambda: core.cef_remove_shortcuts(names), done)

    def restorable(self, names: list) -> bool:
        """Every pick is already on the handheld, so its tile can come back without reinstalling."""
        return bool(names) and all(n in core.NSL_WEB or core.nsl_installed(n) for n in names)

    # ---- add ----
    def add(self):
        names = self.picked()
        if self.restorable(names) and ask(self, "These are already installed.\n\nJust put their tiles back in Steam? "
                                                "(No to reinstall them instead.)"):
            self.clear()

            def done(added):
                if added is None:
                    msg_warn(self, APP_NAME, "Steam's connection for plugins is off (it comes with Decky Loader). "
                                             "Tap Add to Steam again and choose No to reinstall instead.")
                    return
                self.hub.toast(f"Back in your Steam library: {', '.join(added)}")
                self.fix_artwork(only=added, quiet=True)
            BackgroundTask(self, lambda: core.cef_add_shortcuts(names), done)
            return
        cmd = core.nsl_install_cmd(names, self.separate.isChecked())
        if not cmd:
            return
        if not ask(self, "Add these to Steam?\n\n" + "\n".join(f"• {n}" for n in names) +
                   "\n\nThis takes a few minutes."):
            return
        self.last_run = names
        self.hub.runner.submit(f"Adding {len(names)} launcher(s) to Steam", cmd, "nonsteamlaunchers")
        self.clear()
        self.hub.toast("Adding launchers… progress is in the activity log (Settings)")

    def job_done(self, ok: bool):
        """Make sure what was picked really landed: if NSL's scanner didn't add a tile, add it through Steam
        directly, then report anything still missing with the full log."""
        names, self.last_run = self.last_run, []
        self.refresh()
        if not names:
            return
        self.hub.toast("Checking your Steam library…")

        def check():
            live = core.cef_shortcut_names()
            res = core.nsl_results(names, live if live is not None else None)
            added = None
            if res["no_shortcut"]:
                added = core.cef_add_shortcuts(res["no_shortcut"])
                live = core.cef_shortcut_names()
                res = core.nsl_results(names, live if live is not None else None)
            return {"res": res, "added": added, "live": live is not None}
        BackgroundTask(self, check, lambda r: self._checked(names, r))

    def _checked(self, names: list, r: dict):
        if not isinstance(r, dict) or "res" not in r:
            return
        res = r["res"]
        landed = [n for n in names if n not in res["missing"] and n not in res["no_shortcut"]]
        if landed:
            self.fix_artwork(only=landed, quiet=True)
        if not res["missing"] and not res["no_shortcut"]:
            msg_info(self, APP_NAME, "In your Steam library now: " + ", ".join(names) +
                                    ".\n\nFind them under Non-Steam in your library.")
            return
        lines = []
        if res["missing"]:
            lines.append("Didn't finish installing: " + ", ".join(res["missing"]) + ".")
        if res["no_shortcut"]:
            lines.append("Installed, but Steam didn't take the shortcut: " + ", ".join(res["no_shortcut"]) + "." +
                         ("" if r.get("live") else " Steam's connection for plugins is off; make sure Decky "
                                                   "Loader is installed, then restart the handheld."))
        detail = "\n".join(lines) + "\n\n" + core.nsl_log_tail()
        reported = core.queue_report("install-failure", "NonSteamLaunchers: " + "; ".join(lines)[:120], detail,
                                     core._fingerprint("nsl", *sorted(res["missing"] + res["no_shortcut"])))
        if reported and core.LAST_QUEUE == "queued":
            self.hub.send_reports_now()
        msg_warn(self, APP_NAME, "\n\n".join(lines) +
                            ("\n\nThis was reported automatically with the full log." if reported else ""))

    # ---- library art ----
    def fix_artwork(self, *_args, only: list = None, quiet: bool = False, redo: bool = False):
        """Make art for tiles that still show Steam's blank blue (only=[names] after an install). One run at
        a time: requests that arrive meanwhile wait their turn."""
        if getattr(self, "_art_busy", False):
            self._art_queue = getattr(self, "_art_queue", []) + [(only, quiet, redo)]
            return
        self._art_busy = True
        self._art_quiet = quiet
        self.btn_art.setEnabled(False)
        self.btn_art.setText("Looking at your library…")
        BackgroundTask(self, lambda: core.art_plan(only=only, redo=redo),
                       lambda plan: self._art_planned(plan, quiet, redo))

    def _art_ready(self):
        self._art_busy = False
        self.btn_art.setEnabled(True)
        self.btn_art.setText("Fix artwork")
        queue = getattr(self, "_art_queue", [])
        if queue:
            only, quiet, redo = queue.pop(0)
            self._art_queue = queue
            QTimer.singleShot(0, lambda: self.fix_artwork(only=only, quiet=quiet, redo=redo))

    def _art_planned(self, plan, quiet: bool, redo: bool):
        if not isinstance(plan, dict) or "error" in plan:
            self._art_ready()
            if not quiet:
                msg_warn(self, APP_NAME, "Ally Hub couldn't read your Steam library just now. Try again in a "
                                         "moment.")
            return
        todo = plan.get("todo") or []
        if not todo:
            self._art_ready()
            if quiet:
                return
            if not plan.get("tiles"):
                msg_info(self, APP_NAME, "There are no non-Steam games in your library yet.")
            elif plan.get("ours") and not redo:
                if ask(self, "Every non-Steam tile has art already.\n\nRemake the art Ally Hub made earlier? "
                             "Pictures you chose yourself are kept."):
                    self.fix_artwork(redo=True)
            else:
                msg_info(self, APP_NAME, "Every non-Steam tile has art already ✔")
            return
        self._art_made, self._art_todo = [], list(todo)
        self._art_total = len(todo)
        QTimer.singleShot(0, self._art_step)

    def _art_step(self):
        """Draw one tile per turn of the event loop, so the window stays responsive."""
        if self._art_todo:
            t = self._art_todo.pop(0)
            done = self._art_total - len(self._art_todo)
            self.btn_art.setText(f"Making art {done} of {self._art_total}…")
            try:
                pngs, icon = make_art(t)
                if pngs:
                    self._art_made.append((t, pngs, icon))
            except Exception:
                core.app_log("art", f"drawing failed for {t.get('name')}: {traceback.format_exc()[-400:]}")
            QTimer.singleShot(0, self._art_step)
            return
        made, quiet = self._art_made, self._art_quiet
        if not made:
            self._art_ready()
            core.queue_report("install-failure", "Library art: couldn't draw the pictures",
                              "Qt returned no image for any tile (is the SVG image plugin missing?).",
                              core._fingerprint("art-draw"))
            if not quiet:
                msg_warn(self, APP_NAME, "Ally Hub couldn't draw the pictures on this system. This was "
                                         "reported so it can be fixed.")
            return
        self.btn_art.setText("Sending to Steam…")

        def send():
            return [(t["name"], core.apply_art(t["appid"], pngs, icon, t["name"])) for t, pngs, icon in made]
        BackgroundTask(self, send, lambda res: self._art_sent(res, quiet))

    def _art_sent(self, res, quiet: bool):
        self._art_ready()
        if not isinstance(res, list):
            if not quiet:
                msg_warn(self, APP_NAME, "Something went wrong while adding the art. Details are in the "
                                         "activity log (Settings).")
            return
        live = [n for n, r in res if r.get("live")]
        saved = [n for n, r in res if not r.get("live") and r.get("files")]
        failed = [n for n, r in res if not r.get("live") and not r.get("files") and not r.get("kept")]
        if failed:
            core.queue_report("install-failure", "Library art: Steam didn't take the pictures",
                              "Failed: " + ", ".join(failed) + f"\nGrid folder: {core.steam_grid_dir()}",
                              core._fingerprint("art-apply", *sorted(failed)))
        if quiet and not failed:
            if live or saved:
                self.hub.toast("Library art added ✔" if live else "Library art saved. It shows after Steam restarts.")
            return
        parts = []
        if live:
            parts.append("New art in your library: " + ", ".join(live) + ".")
        if saved:
            parts.append("Saved for " + ", ".join(saved) + ". It shows after Steam restarts (the icon needs "
                         "Steam's connection for plugins, which Decky Loader turns on).")
        if failed:
            parts.append("Couldn't add art for " + ", ".join(failed) + ". This was reported automatically.")
        if not parts:
            parts.append("Nothing to change: those tiles already have pictures you chose.")
        (msg_warn if failed else msg_info)(self, APP_NAME, "\n\n".join(parts))

    def own_picture(self, *_args):
        tiles = core.steam_shortcuts()
        if not tiles:
            msg_info(self, APP_NAME, "There are no non-Steam games in your library yet.")
            return
        names = sorted({t["name"] for t in tiles}, key=str.lower)
        name, ok = ask_item(self, "Use my own picture", "Which tile?", names)
        if not ok:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Choose a picture", str(HOME / "Pictures"),
                                              "Pictures (*.png *.jpg *.jpeg)", options=file_dialog_options())
        if not path:
            return
        tile = next(t for t in tiles if t["name"] == name)
        pngs = {"portrait": cover_png(path, 600, 900), "wide": cover_png(path, 920, 430),
                "hero": cover_png(path, 1920, 620)}
        pngs = {k: v for k, v in pngs.items() if v}
        if not pngs:
            msg_warn(self, APP_NAME, "That picture couldn't be opened. Try a PNG or JPG.")
            return
        if getattr(self, "_art_busy", False):
            msg_info(self, APP_NAME, "Ally Hub is making library art right now. Try again in a moment.")
            return
        self._art_busy = True
        self.btn_art.setEnabled(False)
        BackgroundTask(self, lambda: [(name, core.apply_art(tile["appid"], pngs, None, name, mine=True))],
                       lambda res: self._art_sent(res, False))

    # ---- uninstall ----
    def uninstall(self):
        names = self.picked()
        if not names:
            return
        stores = [n for n in names if n in core.NSL_STORES and core.nsl_installed(n)]
        msg = "Remove these from your handheld and your Steam library?\n\n" + "\n".join(f"• {n}" for n in names)
        if stores:
            msg += ("\n\nGames you installed inside a store stay in its Proton prefix until you clean up "
                    "leftovers.")
        if not ask(self, msg):
            return
        self.removing = names
        self.clear()
        cmd = core.nsl_uninstall_cmd(stores)
        if cmd:
            self.hub.runner.submit(f"Removing {len(stores)} launcher(s)", cmd, "nsl-uninstall")
        else:
            self.uninstall_done(True)

    def uninstall_done(self, ok: bool):
        names, self.removing = self.removing, []
        if not names:
            return

        def remove():
            return {"removed": core.cef_remove_shortcuts(names),
                    "still": [n for n in names if core.nsl_installed(n)]}

        def done(r):
            self.refresh()
            if not isinstance(r, dict):
                return
            parts = []
            if r.get("still"):
                parts.append("Couldn't remove the files for: " + ", ".join(r["still"]) + ". Check the activity log (Settings).")
            if r.get("removed") is None:
                parts.append("Steam's connection for plugins is off, so remove the tiles yourself: select one in "
                             "your library, press the menu button, then Manage → Remove non-Steam game.")
            msg_info(self, APP_NAME, "\n\n".join(parts) if parts else
                                    "Removed: " + ", ".join(names) + ". Tap Find leftovers to free the space "
                                                                     "they used.")
        BackgroundTask(self, remove, done)

    # ---- leftovers ----
    def find_leftovers(self):
        self.btn_clean.setEnabled(False)
        self.btn_clean.setText("Looking…")
        BackgroundTask(self, core.nsl_leftovers, self._show_leftovers)

    def _show_leftovers(self, items):
        self.btn_clean.setEnabled(True)
        self.btn_clean.setText("Find leftovers")
        if not isinstance(items, list) or not items:
            msg_info(self, APP_NAME, "Nothing left over. All clean ✔")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Leftover data")
        dv = QVBoxLayout(dlg)
        dv.setContentsMargins(24, 20, 24, 20)
        dv.addWidget(label(f"Found {core.human_size(sum(i['size'] for i in items))} you can free up. "
                           "Untick anything you want to keep.", "cardDesc", wrap=True))
        boxes = []
        for it in items:
            cb = QCheckBox(f"{it['label']}  ({core.human_size(it['size'])})")
            cb.setChecked(not it["warn"])          # risky ones (games inside) start unticked
            dv.addWidget(cb)
            if it["warn"]:
                dv.addWidget(label("⚠ " + it["warn"], "cardWarn", wrap=True))
            boxes.append((cb, it))
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Cancel", dlg.reject))
        row.addWidget(button("Delete selected", dlg.accept, "danger"))
        dv.addLayout(row)
        if run_dialog(dlg) != QDialog.Accepted:
            return
        chosen = [it["path"] for cb, it in boxes if cb.isChecked()]
        cmd = core.nsl_clean_cmd(chosen)
        if cmd:
            self.hub.runner.submit("Cleaning launcher leftovers", cmd, "nsl-clean")


# ==========================================================================
# Game settings: launch options as switches, the Proton picker, "Game won't start?"
# The list and one game's settings are two views of this page (no extra windows), so every pick and
# question below opens as the page's only pop-up.
# ==========================================================================

FSR4_TOOLS = re.compile(r"(?i)ge-proton|cachyos|proton-em")


class GamesPage(QWidget):
    LIST_SIZE = 20

    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self.games, self.live, self.show_all = [], True, False
        self.game, self.settings = None, None
        self.checks, self.other = {}, ""
        self.v = page_shell(self, "Game settings",
                            "Switches instead of typing launch options, the right Proton per game, and help when a "
                            "game won't start. Changes apply the next time the game starts.")
        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        self.v.addLayout(self.body)
        self.v.addStretch()

    # ---- list view ----
    def refresh(self):
        if self.game is None:
            self.body_message("Reading your library…")
            BackgroundTask(self, lambda: {"games": core.game_choices(), "live": core.cef_eval("1") == 1},
                           self._listed)

    def body_message(self, text: str):
        clear_layout(self.body)
        self.body.addWidget(label(text, "cardDesc", wrap=True))

    def _listed(self, r):
        if self.game is not None:
            return
        if not isinstance(r, dict) or "error" in r:
            self.body_message("Couldn't read your library. Try again in a moment.")
            return
        self.games, self.live = r.get("games") or [], bool(r.get("live"))
        self.show_list()

    def show_list(self):
        self.game = None
        clear_layout(self.body)
        self.body.addWidget(self.qam_card())
        self.body.addWidget(label("YOUR GAMES", "section"))
        if not self.live:
            self.body.addWidget(label("⚠ Steam's connection for plugins is off, so settings can be viewed but not "
                                      "saved. It comes with Decky Loader (Store → Mods).", "cardWarn", wrap=True))
        if not self.games:
            self.body.addWidget(label("No games found yet.", "cardDesc"))
            return
        playing = str(core.steam_appid_of(core.agent_state().get("game")) or "")
        games = sorted(self.games, key=lambda g: str(g["appid"]) != playing)
        shown = games if self.show_all else games[:self.LIST_SIZE]
        card = card_frame()
        cv = QVBoxLayout(card)
        cv.setContentsMargins(20, 16, 20, 16)
        cv.setSpacing(6)
        for g in shown:
            text = g["name"] + ("   ▶ playing now" if str(g["appid"]) == playing else "")
            cv.addWidget(button(text, lambda _=False, g=g: self.open_game(g)))
        self.body.addWidget(card)
        if not self.show_all and len(games) > self.LIST_SIZE:
            self.body.addWidget(button(f"Show all {len(games)} games", self.expand))
        QTimer.singleShot(0, lambda: _focus_first(card))

    def expand(self, *_args):
        self.show_all = True
        self.show_list()

    # ---- Quick Access panel ----
    def qam_card(self) -> QWidget:
        have = core.qam_installed()
        card, cv = titled_card("gamepad-2", "#14b8a6", "Quick Access panel",
                               "Ally Hub in the ••• menu while you play: battery and temperatures, this game's "
                               "switches, Game Boost, lighting and a save backup button. Needs Decky Loader.")
        row = QHBoxLayout()
        if not have:
            row.addWidget(button("Add to Quick Access", self.qam_install, "primary"))
        elif core.parse_version(have) < core.parse_version(core.QAM_VERSION):
            row.addWidget(button("Update the panel", self.qam_install, "primary"))
            row.addWidget(button("Remove", self.qam_remove))
        else:
            cv.addWidget(label("✔ In your Quick Access menu. Press ••• while playing and open the plug icon.",
                               "cardMeta", wrap=True))
            row.addWidget(button("Remove", self.qam_remove))
        row.addStretch()
        cv.addLayout(row)
        return card

    def qam_install(self, *_args):
        if not CATALOG_BY_ID["decky"].check(self.hub.state):
            if ask(self, "The Quick Access panel runs inside Decky Loader, which isn't installed yet.\n\nInstall "
                         "Decky Loader now?"):
                self.hub.on_item_action("decky", "install")
            return
        if self.hub.needs_password():
            return
        if not load_config()["agent"].get("enabled") or not core.agent_running():
            self.hub.enable_agent()                       # the panel gets everything from the agent
        self.hub.runner.submit("Adding Ally Hub to Quick Access", core.qam_install_cmd(), "qam-install")

    def qam_remove(self, *_args):
        if self.hub.needs_password():
            return
        if ask(self, "Remove Ally Hub from the Quick Access menu?"):
            self.hub.runner.submit("Removing the Quick Access panel", core.qam_uninstall_cmd(), "qam-remove")

    def qam_done(self, ok: bool, key: str):
        if ok and key == "qam-install":
            self.hub.toast("Ally Hub is in your Quick Access menu: press ••• and open the plug icon.")
        if self.game is None:
            self.show_list()

    # ---- one game ----
    def open_game(self, g: dict):
        self.game = g
        self.body_message(f"Loading {g['name']}…")
        BackgroundTask(self, lambda: core.game_settings(g["appid"], g["kind"]), lambda s: self._loaded(g, s))

    def _loaded(self, g: dict, s):
        if self.game is not g:
            return
        if not isinstance(s, dict) or "error" in s:
            self.game = None
            msg_warn(self, APP_NAME, f"Couldn't read the settings for {g['name']}.")
            self.show_list()
            return
        self.settings = s
        opts = s.get("options", "")
        self.parseable = core.launch_parseable(opts)
        self.flags0 = core.launch_flags(opts) if self.parseable else set()
        self.other = core.set_launch_flags(opts, set()) if self.parseable else opts
        self.other_edited = False
        self.show_game()

    def show_game(self):
        g, s = self.game, self.settings
        clear_layout(self.body)
        top = QHBoxLayout()
        top.addWidget(button("‹ All games", self.back))
        top.addStretch()
        self.body.addLayout(top)
        self.body.addWidget(label(g["name"], "pageTitle"))
        if not s.get("live"):
            self.body.addWidget(label("⚠ Steam's connection for plugins is off, so these can't be saved right now. "
                                      "It comes with Decky Loader.", "cardWarn", wrap=True))
        flags = self.flags0
        card, cv = titled_card("sparkles", "#8b5cf6", "Switches")
        if not self.parseable:
            cv.addWidget(label("This game's launch options have quotes the switches can't change safely. Edit them "
                               "under Other launch options instead.", "cardWarn", wrap=True))
        self.checks = {}
        for key, (title, desc, _kind, _tok) in core.GAME_TOGGLES.items():
            cb = QCheckBox(title)
            cb.setChecked(key in flags)
            cb.setEnabled(self.parseable)
            note = desc
            if key == "lsfg" and not core.LSFG_WRAPPER.exists() and key not in flags:
                cb.setEnabled(False)
                note += " Install Lossless Scaling Frame Gen under Store → Mods first."
            cv.addWidget(cb)
            cv.addWidget(label(note, "cardDesc", wrap=True))
            self.checks[key] = cb
        self.fsr_note = label("", "cardWarn", wrap=True)
        cv.addWidget(self.fsr_note)
        self.body.addWidget(card)

        pcard, pv = titled_card("wine", "#f59e0b", "Proton",
                                "Which compatibility tool runs this game. Steam's default is right for most games.")
        self.tool_combo = QComboBox()
        none = "None (for Linux apps)" if g.get("kind") == "shortcut" else "Steam's default"
        tools = [("", none)] + [t for t in s.get("tools") or [] if t[0]]
        cur = s.get("tool", "")
        if cur and cur not in [t[0] for t in tools]:
            tools.append((cur, cur))
        for name, shown in tools:
            self.tool_combo.addItem(shown, name)
        self.tool_combo.setCurrentIndex(max(0, [t[0] for t in tools].index(cur) if cur in [t[0] for t in tools] else 0))
        self.tool_combo.setEnabled(bool(s.get("live")) and len(tools) > 1)
        self.tool_combo.currentIndexChanged.connect(self.update_fsr_note)
        self.checks["fsr4"].toggled.connect(self.update_fsr_note)
        pv.addWidget(self.tool_combo)
        self.body.addWidget(pcard)
        pcard.setVisible(advanced_mode())                  # built per game, so the mode is read here

        ocard, ov = titled_card("terminal", "#64748b", "Other launch options")
        self.other_label = label(self.other or "None", "cardDesc", wrap=True)
        ov.addWidget(self.other_label)
        orow = QHBoxLayout()
        orow.addWidget(button("Edit", self.edit_other))
        orow.addStretch()
        ov.addLayout(orow)
        self.body.addWidget(ocard)
        ocard.setVisible(advanced_mode() or bool(self.other))   # always shown when the game has some

        row = QHBoxLayout()
        self.btn_save = button("Save", self.save, "primary")
        self.btn_save.setEnabled(bool(s.get("live")))
        row.addWidget(self.btn_save)
        row.addWidget(button("Game won't start?", self.rescue))
        row.addStretch()
        self.body.addLayout(row)
        self.update_fsr_note()
        QTimer.singleShot(0, lambda: _focus_first(card))

    def back(self, *_args):
        self.game = None
        if self.games:
            self.show_list()
        else:
            self.refresh()

    def chosen_tool(self) -> str:
        d = self.tool_combo.currentData()
        return d if isinstance(d, str) else ""

    def update_fsr_note(self, *_args):
        if not self.checks.get("fsr4"):
            return
        tool = self.chosen_tool() or (self.settings or {}).get("tool", "")
        need = self.checks["fsr4"].isChecked() and not FSR4_TOOLS.search(tool or "")
        self.fsr_note.setText("FSR 4 only works with GE-Proton or Proton-CachyOS: pick one under Proton." if need
                              else "")
        self.fsr_note.setVisible(bool(need))

    def edit_other(self, *_args):
        text, ok = ask_text(self, "Other launch options", "Anything else for this game's launch options:", self.other)
        if not ok:
            return
        text = text.strip()
        self.other_edited = True
        if core.launch_parseable(text):
            for key in core.launch_flags(text):           # switches typed by hand show up as switches
                self.checks[key].setChecked(True)
            self.other = core.set_launch_flags(text, set())
            if not self.parseable:
                self.parseable = True
                self.flags0 = set()
                for key, cb in self.checks.items():
                    cb.setEnabled(key != "lsfg" or core.LSFG_WRAPPER.exists())
        else:
            self.other, self.parseable = text, False
            for cb in self.checks.values():
                cb.setEnabled(False)
        self.other_label.setText(self.other or "None")

    def new_options(self) -> str:
        """Launch options to save. Untouched options go back exactly as they were."""
        original = (self.settings or {}).get("options", "")
        if not self.parseable:
            return self.other if self.other_edited else original
        keys = {k for k, cb in self.checks.items() if cb.isChecked()}
        if not self.other_edited and keys == self.flags0:
            return original
        return core.set_launch_flags(self.other if self.other_edited else original, keys)

    def save(self, *_args, note: str = ""):
        g, s = self.game, self.settings
        opts = self.new_options()
        tool = self.chosen_tool()
        tool_arg = tool if tool != s.get("tool", "") else None
        self.btn_save.setEnabled(False)
        self.btn_save.setText("Saving…")
        BackgroundTask(self, lambda: core.apply_game_settings(g["appid"], opts, tool_arg),
                       lambda done: self._saved(g, opts, tool, done, note))

    def _saved(self, g: dict, opts: str, tool: str, done, note: str = ""):
        if self.game is g:
            self.btn_save.setEnabled(True)
            self.btn_save.setText("Save")
        if isinstance(done, list) and "options" in done:
            if self.game is g:
                self.settings = dict(self.settings or {}, options=opts, tool=tool if "tool" in done else
                                     (self.settings or {}).get("tool", ""))
                self.flags0 = core.launch_flags(opts) if core.launch_parseable(opts) else set()
                self.other = core.set_launch_flags(opts, set()) if core.launch_parseable(opts) else opts
                self.other_edited = False
            if note:
                msg_info(self, APP_NAME, note)
            else:
                self.hub.toast(f"Saved. Applies next time you start {g['name']}.")
            core.app_log("games", f"{g['name']} ({g['appid']}): launch options set ({len(opts)} chars)")
        else:
            msg_warn(self, APP_NAME, "Steam didn't take the change. Make sure Decky Loader is running, then try "
                                     "again.")

    # ---- "Game won't start?" ----
    def rescue(self, *_args):
        g, s = self.game, self.settings
        options = []
        if s.get("live") and s.get("tools"):
            options.append("Try a different Proton")
        if s.get("live"):
            options.append("Turn on the troubleshooting log")
        if core.proton_log(g["appid"]):
            options.append("Send the log from the last launch")
        if core.game_prefixes(g["appid"]):
            options.append("Reset its Windows files (the old ones are kept)")
        if g["kind"] == "steam":
            options.append("Check the game's files in Steam")
        if not options:
            msg_info(self, APP_NAME, "There's nothing to try from here for this game.")
            return
        choice, ok = ask_item(self, "Game won't start?", f"What should Ally Hub try for {g['name']}?", options)
        if not ok:
            return
        if choice.startswith("Try a different"):
            names = [t[1] for t in s["tools"] if t[0]]
            pick, ok = ask_item(self, "Pick a Proton", "Newer builds fix most games. GE-Proton helps with videos "
                                                       "and some launchers.", names)
            if ok:
                idx = self.tool_combo.findText(pick)
                if idx >= 0:
                    self.tool_combo.setCurrentIndex(idx)
                self.save()
        elif choice.startswith("Turn on"):
            if not self.parseable:
                msg_warn(self, APP_NAME, "This game's launch options can't be changed with switches. Add "
                                         "PROTON_LOG=1 under Other launch options instead.")
                return
            self.checks["log"].setChecked(True)
            self.save(note=f"Log turned on. Start {g['name']} once, then come back here and choose “Send the log "
                           "from the last launch”.")
        elif choice.startswith("Send"):
            def send():
                return core.queue_report("user", f"{g['name']} won't start"[:110],
                                         f"Reported from Game settings for {g['name']} (app {g['appid']}).\n"
                                         f"Launch options: {s.get('options', '')}\nProton: {s.get('tool') or 'default'}",
                                         core._fingerprint("game-log", str(g["appid"]), str(time.time())),
                                         attachments=[("Proton log", core.proton_log(g["appid"]))], force=True)
            BackgroundTask(self, send, lambda _r: self.hub.toast("Log sent. It'll be looked at in the next daily run."))
        elif choice.startswith("Reset"):
            if core.steam_appid_of(core.agent_state().get("game")) == int(g["appid"]):
                msg_warn(self, APP_NAME, f"Quit {g['name']} first.")
                return
            if ask(self, f"Reset {g['name']}'s Windows files?\n\nSteam makes fresh ones on the next launch. The old "
                         "folder is kept as a backup (saves inside it too), and Storage can clear it later."):
                cmd = core.reset_prefix_cmd(g["appid"])
                if cmd:
                    self.hub.runner.submit(f"Resetting {g['name']}'s Windows files", cmd, "game-reset")
        elif choice.startswith("Check"):
            QDesktopServices.openUrl(QUrl(f"steam://validate/{g['appid']}"))


# ==========================================================================
# Setup: a short walkthrough on first launch (Home > Setup), skippable and re-runnable
# One page that redraws itself per step, so every button and question stays inside the window.
# ==========================================================================

class SetupPage(QWidget):
    STEPS = ["welcome", "password", "gamemode", "essentials", "lighting", "features", "reports", "done"]

    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self.step = 0
        self.essentials = {}
        self.v = page_shell(self, "Setup", "A minute to get your Ally ready. Everything here can be changed later.")
        self.dots = label("", "cardMeta")
        self.v.addWidget(self.dots)
        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        self.v.addLayout(self.body)
        nav = QHBoxLayout()
        self.btn_back = button("‹ Back", self.back)
        self.btn_skip = button("Skip setup", self.finish)
        self.btn_next = button("Next ›", self.next, "primary")
        nav.addWidget(self.btn_back)
        nav.addStretch()
        nav.addWidget(self.btn_skip)
        nav.addWidget(self.btn_next)
        self.v.addLayout(nav)
        self.v.addStretch()

    def steps(self) -> list:
        """Steps that apply here: lighting only with ring lights, reports only on a device with a report key."""
        out = list(self.STEPS)
        if not core.find_leds():
            out.remove("lighting")
        if not core.github_token():
            out.remove("reports")
        return out

    def refresh(self):
        steps = self.steps()
        self.step = max(0, min(self.step, len(steps) - 1))
        name = steps[self.step]
        self.dots.setText(f"Step {self.step + 1} of {len(steps)}")
        self.btn_back.setEnabled(self.step > 0)
        self.btn_skip.setVisible(name != "done")
        self.btn_next.setText("Finish" if name == "done" else "Next ›")
        clear_layout(self.body)
        getattr(self, "step_" + name)()
        QTimer.singleShot(0, lambda: _focus_first(self))

    def back(self, *_args):
        self.step -= 1
        self.refresh()

    def next(self, *_args):
        if self.steps()[self.step] == "done":
            self.finish()
            return
        self.step += 1
        self.refresh()

    def finish(self, *_args):
        update_config(lambda c: c.setdefault("setup", {}).__setitem__("done", True))
        if core.in_steam_library():
            self.hub.launchers.fix_artwork(only=["Ally Hub"], quiet=True)
        self.step = 0
        self.hub.go("Overview")
        self.hub.update_setup_chip()
        self.hub.refresh()

    # ---- pieces ----
    def card(self, icon: str, color: str, title: str, desc: str) -> QVBoxLayout:
        c, cv = titled_card(icon, color, title, desc)
        self.body.addWidget(c)
        return cv

    def status_row(self, cv: QVBoxLayout, done: bool, done_text: str, todo_text: str, btn_text: str, fn):
        row = QHBoxLayout()
        pill = label("", "pill")
        set_pill(pill, "DONE" if done else "TO DO", "on" if done else "off")
        row.addWidget(pill)
        row.addWidget(label(done_text if done else todo_text, "cardDesc", wrap=True), 1)
        if not done and fn:
            row.addWidget(button(btn_text, fn, "primary"))
        cv.addLayout(row)

    # ---- steps ----
    def step_welcome(self):
        self.card("gamepad-2", "#e11d48", "Welcome to Ally Hub",
                  "Mods and apps in one tap, smoother games, lighting, save snapshots and more, all working with the "
                  "controller. The next few steps set up the basics. Skip anything you don't want.")

    def step_password(self):
        cv = self.card("lock-keyhole", "#f59e0b", "Sudo password",
                       "SteamOS ships without one. Ally Hub needs it to install Decky, plugins and system tweaks, "
                       "and asks for it only when a task needs it.")
        if self.hub.state.get("password") is False:
            self.hub.refresh_password()          # may have been set since the last look
        pw = self.hub.state.get("password") is not False
        self.status_row(cv, pw, "A password is set.", "No password yet.", "Set password", self.hub.set_password)
        if not pw:
            cv.addWidget(label("A terminal opens to set it. This page updates when you close it. If it asks for "
                               "your current password, you already have one: close it and tap I already have one.",
                               "cardMeta", wrap=True))
            r = QHBoxLayout()
            r.addWidget(button("Check again", lambda: (self.hub.refresh_password(), self.refresh())))
            r.addWidget(button("I already have one", self.already_have_password))
            r.addStretch()
            cv.addLayout(r)

    def already_have_password(self, *_args):
        self.hub.assume_password()
        self.hub.health.refresh_notices(self.hub.state)
        self.next()

    def step_gamemode(self):
        cv = self.card("monitor-play", "#0ea5e9", "Game Mode",
                       "Open Ally Hub from your Steam library and use it with the controller.")
        self.status_row(cv, core.in_steam_library(), "Ally Hub is in your Game Mode library.",
                        "Not in your Steam library yet.", "Add to Steam",
                        lambda: (self.hub.add_to_steam(), QTimer.singleShot(4000, self.refresh)))
        cfg = load_config()
        on = bool(cfg["agent"].get("enabled")) and core.agent_running()
        self.status_row(cv, on, "The background helper is running.",
                        "The background helper is off. It powers the Quick Access panel, Game Boost, save snapshots "
                        "and sleep tracking.", "Turn on",
                        lambda: (self.hub.enable_agent(), QTimer.singleShot(3000, self.refresh)))

    def step_essentials(self):
        cv = self.card("download", "#22c55e", "Essentials",
                       "Pick what to install now. Nothing installs until you tap Install.")
        # the same essentials as Store > Browse > Essentials (catalog items marked recommended), plus the panel
        st = self.hub.state
        options = [("decky", "Decky Loader", "Plugins in Game Mode's ••• menu. Most Game Mode extras need it.",
                    CATALOG_BY_ID["decky"].check(st), True),
                   ("qam", "Ally Hub in Quick Access", "Battery, temps, game switches and lighting while you play.",
                    bool(core.qam_installed()), True)]
        options += [(i.id, i.name, i.desc, i.check(st), i.id == core.LUDUSAVI_ID)
                    for i in CATALOG if i.recommended and i.id != "decky"]
        self.essentials = {}
        for key, title, desc, have, preset in options:
            cb = QCheckBox(title + ("  ✔ installed" if have else ""))
            cb.setChecked(preset and not have)
            cb.setEnabled(not have)
            cv.addWidget(cb)
            cv.addWidget(label(desc, "cardMeta", wrap=True))
            self.essentials[key] = (cb, have)
        r = QHBoxLayout()
        r.addWidget(button("Install selected", self.install_essentials, "primary"))
        r.addStretch()
        cv.addLayout(r)

    def install_essentials(self, *_args):
        pick = [k for k, (cb, have) in self.essentials.items() if cb.isChecked() and not have]
        if not pick:
            self.hub.toast("Nothing selected")
            return
        root = [k for k in pick if k == "qam" or (k in CATALOG_BY_ID and "." not in k)]   # Flatpaks need no password
        if root and self.hub.needs_password():
            return
        if "decky" in pick:
            self.hub.on_item_action("decky", "install")
        for iid in pick:
            if iid in CATALOG_BY_ID and iid != "decky":
                self.hub.on_item_action(iid, "install")
        if "qam" in pick:
            if "decky" in pick:
                self.hub.qam_after_decky = True              # the panel goes in once Decky is there
            else:
                self.hub.games.qam_install()
        self.hub.toast("Installing… progress is in the activity log (Settings)")

    def step_lighting(self):
        cv = self.card("lightbulb", "#8b5cf6", "Joystick ring lighting",
                       "Pick who runs the rings. HueSync is a Decky plugin; Ally Hub lighting has effects, battery "
                       "and per-game colors. You can switch any time under Customize → Lighting.")
        shelved = core.lighting_shelved()
        cv.addWidget(label("Now: " + ("HueSync" if shelved else "Ally Hub lighting"), "cardDesc"))
        r = QHBoxLayout()
        r.addWidget(button("Use HueSync", lambda: (self.hub.use_huesync_lighting(), self.refresh())))
        r.addWidget(button("Use Ally Hub lighting", lambda: (self.hub.use_allyhub_lighting(), self.refresh())))
        r.addStretch()
        cv.addLayout(r)

    def step_features(self):
        cv = self.card("rocket", "#f97316", "A few favorites",
                       "Turn on what you like. Each one has more options under Games.")
        cfg = load_config()
        boost = QCheckBox("Game Boost: the CPU's performance setting while you play")
        boost.setChecked(bool((cfg.get("performance") or {}).get("boost")))
        boost.toggled.connect(lambda on: self.hub.performance.set_boost(on))
        cv.addWidget(boost)
        tm = QCheckBox("Save time machine: snapshot a game's saves every time it starts")
        tm.setChecked(bool((cfg.get("saves") or {}).get("time_machine")))
        tm.toggled.connect(lambda on: self.hub.saves.set_on(on))
        cv.addWidget(tm)
        cv.addWidget(label("Sleep tracking is automatic once the background helper runs.", "cardMeta", wrap=True))

    def step_reports(self):
        cv = self.card("bug", "#e11d48", "Error reports",
                       "Problems are filed on GitHub with personal details removed, so they get fixed in the "
                       "daily updates.")
        cb = QCheckBox("Send error reports")
        cb.setChecked(bool(load_config()["updates"].get("reporting")))
        cb.toggled.connect(lambda on: update_config(lambda c: c["updates"].__setitem__("reporting", bool(on))))
        cv.addWidget(cb)

    def step_done(self):
        left = [t for _k, t, done in core.setup_checklist(self.hub.state) if not done]
        cv = self.card("sparkles", "#22c55e", "All set" if not left else "Almost there",
                       "Ally Hub is ready. Home shows your battery and temps; everything else is in the tabs above."
                       if not left else "Still to do (Home keeps a reminder): " + "; ".join(left) + ".")
        cv.addWidget(label("Run this again any time: Settings → General → Run setup again.", "cardMeta", wrap=True))


# ==========================================================================
# Save time machine: snapshots of each game's saves, taken as it starts, restorable from Game Mode
# ==========================================================================

class SavesPage(QWidget):
    KEEP = [(3, "Keep 3 per game"), (5, "Keep 5 per game"), (10, "Keep 10 per game")]

    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self.snaps, self.undo = {}, {}
        v = page_shell(self, "Saves",
                       "A safety net for your progress: Ally Hub snapshots a game's saves every time it starts, so "
                       "a corrupted save or a choice you regret is one restore away.")
        card, cv = titled_card("save", "#22c55e", "Save time machine",
                               "Uses Ludusavi, which knows where thousands of games keep their saves, including "
                               "Windows games under Proton. Snapshots stay on your handheld.")
        self.tm_cb = QCheckBox("Snapshot a game's saves every time it starts")
        self.tm_cb.toggled.connect(self.set_on)
        cv.addWidget(self.tm_cb)
        kr = QHBoxLayout()
        self.keep = QComboBox()
        for _n, text in self.KEEP:
            self.keep.addItem(text)
        self.keep.currentIndexChanged.connect(self.set_keep)
        kr.addWidget(self.keep)
        kr.addStretch()
        cv.addLayout(kr)
        self.need = QHBoxLayout()
        self.btn_ludusavi = button("Install Ludusavi", lambda: hub.on_item_action(core.LUDUSAVI_ID, "install"),
                                   "primary")
        self.need.addWidget(self.btn_ludusavi)
        self.need.addStretch()
        cv.addLayout(self.need)
        self.status = label("", "cardMeta", wrap=True)
        cv.addWidget(self.status)
        v.addWidget(card)

        v.addWidget(label("YOUR SNAPSHOTS", "section"))
        lcard = card_frame()
        self.list_box = QVBoxLayout(lcard)
        self.list_box.setContentsMargins(20, 16, 20, 16)
        self.list_box.setSpacing(6)
        v.addWidget(lcard)
        row = QHBoxLayout()
        self.btn_reload = button("Refresh list", self.load)
        row.addWidget(self.btn_reload)
        row.addStretch()
        v.addLayout(row)
        v.addStretch()
        self._loading = False

    def refresh(self):
        cfg = load_config().get("saves") or {}
        self._loading = True
        self.tm_cb.setChecked(bool(cfg.get("time_machine")))
        keep = int(cfg.get("keep", 5) or 5)
        self.keep.setCurrentIndex(next((i for i, (n, _t) in enumerate(self.KEEP) if n == keep), 1))
        self._loading = False
        have = bool(core.CATALOG_BY_ID[core.LUDUSAVI_ID].check(self.hub.state)) if core.LUDUSAVI_ID in core.CATALOG_BY_ID \
            else False
        self.btn_ludusavi.setVisible(not have)
        on = bool(cfg.get("time_machine"))
        if not have:
            self.status.setText("Needs Ludusavi, a free app from Flathub.")
        elif on and not core.agent_running():
            self.status.setText("Needs the background helper (Settings → General), which takes the snapshots.")
        elif on:
            st = core.read_json(core.TM_STATE, {}) or {}
            last = max(st.values(), key=lambda r: r.get("t", 0), default=None)
            self.status.setText("On. " + (f"Last snapshot: {last.get('game') or 'a game'}, "
                                          f"{time.strftime('%b %-d %H:%M', time.localtime(last['t']))}"
                                          f"{'' if last.get('rc') == 0 else ' (failed)'}." if last else
                                          "Start a game and its saves are snapshotted."))
        else:
            self.status.setText("Off.")
        self.load()

    def set_on(self, on: bool):
        if self._loading:
            return
        update_config(lambda c: c.setdefault("saves", {}).__setitem__("time_machine", bool(on)))
        if on and (not load_config()["agent"].get("enabled") or not core.agent_running()):
            self.hub.enable_agent()
        self.refresh()

    def set_keep(self, idx: int):
        if self._loading or idx < 0:
            return
        update_config(lambda c: c.setdefault("saves", {}).__setitem__("keep", self.KEEP[idx][0]))

    def load(self, *_args):
        clear_layout(self.list_box)
        self.list_box.addWidget(label("Looking for snapshots…", "cardDesc"))
        BackgroundTask(self, lambda: {"tm": core.tm_snapshots(), "undo": core.tm_snapshots(core.TM_BEFORE_RESTORE)},
                       self._loaded)

    def _loaded(self, res):
        clear_layout(self.list_box)
        if not isinstance(res, dict) or "error" in res:
            self.list_box.addWidget(label("Couldn't read the snapshots. Is Ludusavi installed?", "cardDesc"))
            return
        snaps = res.get("tm") if "tm" in res else res
        self.undo = res.get("undo") or {} if "tm" in res else {}
        self.snaps = snaps
        if not snaps:
            self.list_box.addWidget(label("No snapshots yet. Turn the time machine on and play something.", "cardDesc"))
            return
        for title in sorted(snaps, key=lambda t: snaps[t][0].get("when", ""), reverse=True):
            backs = snaps[title]
            self.list_box.addWidget(button(f"{title}   ·   {len(backs)} snapshot{'s' if len(backs) != 1 else ''}, "
                                           f"newest {core.when_text(backs[0].get('when', ''))}",
                                           lambda _=False, t=title: self.pick(t)))

    def pick(self, title: str):
        backs = self.snaps.get(title) or []
        if not backs:
            return
        undo = (self.undo.get(title) or [None])[0]
        labels, seen = [], {}
        for b in backs:
            text = core.when_text(b.get("when", "")) + ("  (locked)" if b.get("locked") else "")
            seen[text] = seen.get(text, 0) + 1
            labels.append(text if seen[text] == 1 else f"{text} ({seen[text]})")    # every choice unique
        undo_label = f"Undo the last restore (saves from {core.when_text(undo.get('when', ''))})" if undo else None
        choice, ok = ask_item(self, title, "Restore the saves from which session start?",
                              ([undo_label] if undo_label else []) + labels)
        if not ok:
            return
        st = core.agent_state()
        game = st.get("game")
        running = core.ludusavi_title_cached(core.steam_appid_of(game), st.get("game_name") or "") if game else ""
        if game and (running == title or str(st.get("game_name") or "").lower() == title.lower()):
            msg_warn(self, APP_NAME, f"Quit {title} first, then restore.")
            return
        if choice == undo_label:
            if ask(self, f"Put back {title}'s saves from just before the last restore?"):
                self.hub.runner.submit(f"Undoing the last restore of {title}",
                                       core.tm_restore_cmd(title, undo["name"], undo=True), "tm-restore")
            return
        b = backs[labels.index(choice)]
        if ask(self, f"Restore {title} to {choice}?\n\nYour saves as they are now are kept first, and the restore "
                     "only runs if that worked. “Undo the last restore” puts them back."):
            self.hub.runner.submit(f"Restoring {title}'s saves", core.tm_restore_cmd(title, b["name"]), "tm-restore")

    def job_done(self, ok: bool):
        self.hub.toast("Saves restored ✔" if ok else "The restore didn't finish. See the activity log (Settings).")
        self.load()


# ==========================================================================
# Sleep guardian: battery used per sleep, what woke the handheld, sleeps that failed
# ==========================================================================

class SleepPage(QWidget):
    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        v = page_shell(self, "Sleep",
                       "Ally Hub watches every sleep: how much battery it cost, what woke the handheld, and sleeps "
                       "that didn't work. If something's wrong, it says what and offers a fix.")
        card, cv = titled_card("moon", "#6366f1", "Recent sleeps")
        self.summary = label("", "cardDesc", wrap=True)
        cv.addWidget(self.summary)
        self.list_box = QVBoxLayout()
        self.list_box.setSpacing(2)
        cv.addLayout(self.list_box)
        v.addWidget(card)
        v.addWidget(label("WHAT ALLY HUB NOTICED", "section"))
        self.find_box = QVBoxLayout()
        self.find_box.setSpacing(12)
        v.addLayout(self.find_box)
        wcard, wv = titled_card("power", "#64748b", "Devices that can't wake it",
                                "USB devices you've stopped from waking the handheld. The power button always works.")
        self.nowake_box = QVBoxLayout()
        wv.addLayout(self.nowake_box)
        self.wake_block = block(wcard, heading="Waking the handheld")   # Advanced, or whenever something's blocked
        v.addWidget(self.wake_block)
        row = QHBoxLayout()
        row.addWidget(button("Send the sleep details", self.send_details))
        row.addStretch()
        v.addLayout(row)
        v.addStretch()

    def refresh(self):
        log = core.sleep_log()
        clear_layout(self.list_box)
        if not log:
            self.summary.setText("No sleeps recorded yet. Put the handheld to sleep once and the details show up "
                                 "here." + ("" if core.agent_running() else " Needs the background helper "
                                                                            "(Settings → General)."))
        else:
            last = log[-1]
            used = ("charging" if last.get("charging") else
                    f"used {last['drop']:.0f}% of the battery" if last.get("drop") is not None else "battery unknown")
            rate = f" ({last['per_hour']:.1f}% per hour)" if last.get("per_hour") is not None else ""
            woke = f" Woken by {', '.join(last['woke_by'])}." if last.get("woke_by") else ""
            self.summary.setText(f"Last sleep: {core.duration_text(last['slept'])}, {used}{rate}.{woke}")
            for e in reversed(log[-8:]):
                when = time.strftime("%b %-d %H:%M", time.localtime(e.get("end", 0)))
                bits = [core.duration_text(e.get("slept", 0))]
                if e.get("charging"):
                    bits.append("charging")
                elif e.get("drop") is not None:
                    bits.append(f"-{e['drop']:.0f}%")
                if e.get("failed"):
                    bits.append("failed")
                self.list_box.addWidget(label(f"{when}   " + " · ".join(bits), "cardMeta"))
        clear_layout(self.find_box)
        findings = core.sleep_findings(log)
        if not findings:
            self.find_box.addWidget(label("Nothing wrong with recent sleeps ✔" if log else
                                          "Nothing to say yet.", "cardDesc"))
        for f in findings:
            fc, fv = titled_card("moon", "#f59e0b", f["title"], f["detail"])
            if f.get("fix") and f["fix"].get("kind") == "nowake":
                r = QHBoxLayout()
                r.addWidget(button(f"Stop {f['fix']['name']} waking it", lambda _=False, fx=f["fix"]: self.stop_wake(fx),
                                   "primary"))
                r.addStretch()
                fv.addLayout(r)
            self.find_box.addWidget(fc)
        clear_layout(self.nowake_box)
        blocked = (load_config().get("sleep") or {}).get("no_wake") or []
        self.wake_block.setVisible(advanced_mode() or bool(blocked))     # never hide the way to undo a block
        if not blocked:
            self.nowake_box.addWidget(label("None. Every device can wake it.", "cardDesc"))
        for d in blocked:
            r = QHBoxLayout()
            r.addWidget(label(d.rsplit("/", 1)[-1], "cardDesc"), 1)
            r.addWidget(button("Allow again", lambda _=False, dp=d: self.allow_wake(dp)))
            self.nowake_box.addLayout(r)

    def _apply_nowake(self, devpaths: list, label_text: str, allow: list = ()):
        """Run the rule job; the saved list only changes once the job worked (see job_done)."""
        if self.hub.needs_password():
            return
        cmd = core.nowake_cmd(devpaths, allow)
        if cmd:
            self._pending_nowake = sorted(set(devpaths))
            self.hub.runner.submit(label_text, cmd, "sleep-nowake")

    def stop_wake(self, fix: dict):
        if not ask(self, f"Stop {fix['name']} from waking the handheld?\n\nThe power button still wakes it, and you "
                         "can allow it again here."):
            return
        cur = (load_config().get("sleep") or {}).get("no_wake") or []
        self._apply_nowake(cur + [fix["devpath"]], f"Stopping {fix['name']} from waking the handheld")

    def allow_wake(self, devpath: str):
        cur = [d for d in (load_config().get("sleep") or {}).get("no_wake") or [] if d != devpath]
        self._apply_nowake(cur, "Letting a device wake the handheld again", allow=[devpath])

    def send_details(self, *_args):
        def send():
            details = json.dumps({"stats": core.suspend_stats(), "findings": core.sleep_findings()}, indent=1)
            return core.queue_report("user", "Sleep details from the Sleep page",
                                     "Sent from Home → Battery & sleep.\n\n" + details,
                                     core._fingerprint("sleep", str(time.time())),
                                     attachments=[("Sleep log", json.dumps(core.sleep_log()[-30:], indent=1)),
                                                  ("Wakeup sources", json.dumps(core.wakeup_sources(), indent=1))],
                                     force=True)
        BackgroundTask(self, send, lambda _r: self.hub.toast("Sleep details sent. They'll be looked at in the next "
                                                             "daily run."))

    def job_done(self, ok: bool):
        pending = getattr(self, "_pending_nowake", None)
        self._pending_nowake = None
        if ok and pending is not None:
            update_config(lambda c: c.setdefault("sleep", {}).__setitem__("no_wake", pending))
        self.hub.toast("Saved ✔" if ok else "That didn't work. See the activity log (Settings).")
        self.refresh()


# ==========================================================================
# Storage saver: where the space went, and what Steam left behind
# ==========================================================================

class StoragePage(QWidget):
    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self.result = None
        self.boxes = []
        v = page_shell(self, "Storage",
                       "See where your space went and clear what Steam leaves behind after you uninstall games. "
                       "Nothing is deleted until you pick it.")
        card, cv = titled_card("hard-drive", "#0ea5e9", "Your drives")
        self.drive_box = QVBoxLayout()
        self.drive_box.setSpacing(10)
        cv.addLayout(self.drive_box)
        row = QHBoxLayout()
        self.btn_scan = button("Scan my storage", self.scan, "primary")
        row.addWidget(self.btn_scan)
        row.addStretch()
        cv.addLayout(row)
        self.status = label("", "cardMeta", wrap=True)
        cv.addWidget(self.status)
        v.addWidget(card)

        v.addWidget(label("CAN GO", "section"))
        ccard = card_frame()
        self.clean_v = QVBoxLayout(ccard)
        self.clean_v.setContentsMargins(20, 16, 20, 16)
        self.clean_v.setSpacing(8)
        self.clean_box = QVBoxLayout()
        self.clean_box.setSpacing(6)
        self.clean_v.addLayout(self.clean_box)
        crow = QHBoxLayout()
        self.btn_clean = button("Free up space", self.clean, "primary")
        self.btn_clean.setEnabled(False)
        crow.addWidget(self.btn_clean)
        crow.addStretch()
        self.clean_v.addLayout(crow)
        v.addWidget(ccard)

        v.addWidget(label("BIGGEST GAMES", "section"))
        gcard = card_frame()
        self.games_box = QVBoxLayout(gcard)
        self.games_box.setContentsMargins(20, 16, 20, 16)
        self.games_box.setSpacing(6)
        v.addWidget(gcard)
        v.addStretch()
        self.show_result(None)

    def refresh(self):
        self.show_drives([])

    def show_drives(self, drives: list):
        clear_layout(self.drive_box)
        if not drives:
            drives = []
            for p in [core.HOME] + core.sd_cards():
                try:
                    u = shutil.disk_usage(p)
                    drives.append({"label": "SD card" if str(p).startswith("/run/media/") else "Internal storage",
                                   "free": u.free, "total": u.total})
                except OSError:
                    pass
        for d in drives:
            self.drive_box.addWidget(label(f"{d['label']}: {core.human_size(d['free'])} free of "
                                           f"{core.human_size(d['total'])}", "cardDesc"))
            bar = QProgressBar()
            bar.setRange(0, 1000)
            bar.setValue(int(1000 * (1 - d["free"] / d["total"])) if d["total"] else 0)
            bar.setTextVisible(False)
            bar.setFixedHeight(10)
            self.drive_box.addWidget(bar)

    def scan(self, *_args):
        self.btn_scan.setEnabled(False)
        self.btn_scan.setText("Scanning… (up to a minute)")
        BackgroundTask(self, core.storage_scan, self._scanned)

    def _scanned(self, res):
        self.btn_scan.setEnabled(True)
        self.btn_scan.setText("Scan again")
        if not isinstance(res, dict) or "error" in res:
            self.status.setText("The scan didn't finish. Try again in a moment.")
            if isinstance(res, dict) and res.get("error"):
                core.app_log("storage", f"scan failed: {res.get('error')}")
            return
        self.show_result(res)

    def show_result(self, res):
        self.result = res
        clear_layout(self.clean_box)
        clear_layout(self.games_box)
        self.boxes = []
        if res is None:
            self.status.setText("Tap Scan to see what's using your space.")
            self.clean_box.addWidget(label("Scan first to find leftovers.", "cardDesc"))
            self.games_box.addWidget(label("Scan first to see your biggest games.", "cardDesc"))
            self.update_clean_button()
            return
        self.show_drives(res.get("drives") or [])
        items = res.get("items") or []
        total = sum(i["size"] for i in items)
        self.status.setText(f"Found {core.human_size(total)} of leftovers." if items else "No leftovers found. All clean ✔")
        if not items:
            self.clean_box.addWidget(label("Nothing left behind by removed games.", "cardDesc"))
        for it in items:
            cb = QCheckBox(f"{it['label']}  ({core.human_size(it['size'])})")
            cb.setChecked(it.get("group") == "safe")
            cb.toggled.connect(self.update_clean_button)
            self.clean_box.addWidget(cb)
            if it.get("warn"):
                self.clean_box.addWidget(label("⚠ " + it["warn"], "cardWarn", wrap=True))
            self.boxes.append((cb, it))
        games = res.get("games") or []
        if not games:
            self.games_box.addWidget(label("No installed Steam games found.", "cardDesc"))
        for g in games[:25]:
            b = button(f"{g['name']}   {core.human_size(g['total'])}", lambda _=False, g=g: self.game_menu(g))
            self.games_box.addWidget(b)
            parts = [f"Game {core.human_size(g['size'])}"]
            if g.get("prefix"):
                parts.append(f"Windows files {core.human_size(g['prefix'])}")
            if g.get("shaders"):
                parts.append(f"Shader cache {core.human_size(g['shaders'])}")
            if str(g.get("lib", "")).startswith("/run/media/"):
                parts.append("on the SD card")
            self.games_box.addWidget(label(" · ".join(parts), "cardMeta"))
        self.update_clean_button()

    def picked(self) -> list:
        return [it for cb, it in self.boxes if cb.isChecked()]

    def update_clean_button(self, *_):
        chosen = self.picked()
        size = sum(i["size"] for i in chosen)
        self.btn_clean.setText(f"Free up {core.human_size(size)}" if chosen else "Free up space")
        self.btn_clean.setEnabled(bool(chosen))

    def clean(self, *_args):
        chosen = self.picked()
        cmd = core.storage_clean_cmd([i["path"] for i in chosen])
        if not cmd:
            return
        size = core.human_size(sum(i["size"] for i in chosen))
        risky = [i for i in chosen if i.get("group") != "safe"]
        msg = f"Delete {len(chosen)} item(s) and free {size}?"
        if risky:
            msg += "\n\nThis includes files that can hold saves:\n" + "\n".join(f"• {i['label']}" for i in risky)
        if ask(self, msg):
            self.hub.runner.submit(f"Freeing up {size}", cmd, "storage-clean")

    def game_menu(self, g: dict):
        options = []
        if g.get("shaders") and g.get("shader_paths"):
            options.append(f"Clear its shader cache ({core.human_size(g['shaders'])}, rebuilds while you play)")
        options.append("Uninstall it in Steam")
        choice, ok = ask_item(self, g["name"], f"{g['name']} uses {core.human_size(g['total'])}.", options)
        if not ok:
            return
        if choice.startswith("Clear"):
            cmd = core.storage_clean_cmd(g["shader_paths"])
            if cmd:
                self.hub.runner.submit(f"Clearing {g['name']}'s shader cache", cmd, "storage-clean")
        else:
            QDesktopServices.openUrl(QUrl(f"steam://uninstall/{g['appid']}"))

    def job_done(self, ok: bool):
        self.hub.toast("Space freed ✔" if ok else "Some files couldn't be deleted. See the activity log (Settings).")
        self.scan()


# ==========================================================================
# Performance: Game Boost and the Tune-up, ideas from CachyOS and Bazzite
# ==========================================================================

BOOST_WORDS = {"performance": "full performance", "balance_performance": "performance (battery friendly)"}
TUNE_PILLS = {"on": ("On", "on"), "off": ("Off", "off"), "na": ("Skip", "off")}


class PerformancePage(QWidget):
    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        self._loading = False
        v = page_shell(self, "Performance",
                       "Smoother games, with ideas from CachyOS and Bazzite. Everything here can be undone.")

        card, cv = titled_card(
            "rocket", "#f97316", "Game Boost",
            "When a game starts, the CPU switches to its performance setting and Ally Hub pauses its own "
            "backups, updates and reports. Everything goes back when you quit. TDP and GPU clocks stay "
            "with SteamOS. On battery it boosts a little less, to save power.")
        self.boost_cb = QCheckBox("Boost my games")
        self.boost_cb.toggled.connect(self.set_boost)
        cv.addWidget(self.boost_cb)
        self.boost_status = label("", "cardDesc", wrap=True)
        cv.addWidget(self.boost_status)
        row = QHBoxLayout()
        self.btn_boost_perm = button("Allow Game Boost", self.allow_boost, "primary")
        row.addWidget(self.btn_boost_perm)
        row.addStretch()
        cv.addLayout(row)
        v.addWidget(card)

        tune_head = label("TUNE-UP", "section")
        tcard, tv = titled_card(
            "memory-stick", "#22c55e", "System tune-up",
            "The memory and kernel settings that Bazzite, CachyOS and CryoUtilities ship. One tap applies "
            "everything your SteamOS supports, and Undo all puts it back.")
        self.tune_box = QVBoxLayout()
        self.tune_box.setSpacing(8)
        tv.addLayout(self.tune_box)
        tr = QHBoxLayout()
        self.btn_tune = button("Apply tune-up", self.apply_tuneup, "primary")
        self.btn_untune = button("Undo all", self.undo_tuneup)
        tr.addWidget(self.btn_tune)
        tr.addWidget(self.btn_untune)
        tr.addStretch()
        tv.addLayout(tr)
        v.addWidget(adv(block(tune_head, tcard)))          # expert control: Advanced only

        v.addWidget(label("EVERY GAME", "section"))
        gcard, gv = titled_card(
            "sparkles", "#ef4444", "Upscaling for every game",
            "Set once and every game gets it, the way Bazzite does it: no launch options to edit. "
            "Changes apply after you restart the handheld.")
        self.env_checks = {}
        for key, (_vars, title, desc) in core.GAME_ENV_OPTIONS.items():
            cb = QCheckBox(title)
            cb.toggled.connect(lambda on, k=key: self.set_game_env(k, on))
            gv.addWidget(cb)
            gv.addWidget(label(desc, "cardDesc", wrap=True))
            self.env_checks[key] = cb
        self.env_status = label("", "cardMeta", wrap=True)
        gv.addWidget(self.env_status)
        v.addWidget(gcard)
        v.addStretch()

    # live Game Boost status while the page is open
    def showEvent(self, ev):
        super().showEvent(ev)
        if not hasattr(self, "_timer"):
            self._timer = QTimer(self)
            self._timer.timeout.connect(self.refresh_boost)
        self._timer.start(3000)

    def hideEvent(self, ev):
        super().hideEvent(ev)
        if hasattr(self, "_timer"):
            self._timer.stop()

    def refresh(self):
        self.refresh_boost()
        self.refresh_tuneup()
        self.refresh_game_env()

    def refresh_game_env(self):
        self._loading = True
        for key, cb in self.env_checks.items():
            cb.setChecked(core.game_env_enabled(key))
        self._loading = False
        on = [k for k in self.env_checks if core.game_env_enabled(k)]
        env = core.process_env()
        lines = []
        if on and env is not None:
            pending = [core.GAME_ENV_OPTIONS[k][1] for k in on if not core.game_env_live(k, env)]
            lines.append(f"Waiting for a restart: {', '.join(pending)}." if pending else "✔ Active in Steam right now.")
        elif on:
            lines.append("Saved. It takes effect the next time Steam starts.")
        if on and "fsr4" in on and not core.custom_protons():
            lines.append("No GE-Proton or Proton-CachyOS found. Install GE-Proton with ProtonPlus (Store → Apps), "
                         "then pick it under a game's Properties → Compatibility.")
        elif core.custom_protons():
            lines.append("Proton builds that support this: " + ", ".join(core.custom_protons()[-3:]) + ".")
        self.env_status.setText("\n".join(lines))

    def refresh_boost(self):
        cfg = load_config()
        on = bool((cfg.get("performance") or {}).get("boost"))
        self._loading = True
        self.boost_cb.setChecked(on)
        self._loading = False
        backend = core.boost_backend()
        ready = core.boost_ready()
        self.boost_cb.setEnabled(bool(backend))
        self.btn_boost_perm.setVisible(on and backend == "epp" and not ready)
        st = core.agent_state()
        if not backend:
            text = "This SteamOS kernel doesn't let apps change the CPU's performance setting."
        elif not on:
            text = "Off."
        elif not ready:
            text = "Needs a one-time permission to change the CPU setting."
        elif not cfg["agent"].get("enabled") or not core.agent_running():
            text = "Needs the background helper (Settings → General), which runs Game Boost."
        elif st.get("game"):
            name = st.get("game_name") or "your game"
            note = st.get("boost") or ""
            text = (f"Boosting {name}: CPU set to {BOOST_WORDS.get(note, note)}." if note in BOOST_WORDS
                    else f"Playing {name}. On battery, Game Boost waits until you plug in."
                    if note == "unavailable" else f"Playing {name}.")
        else:
            text = "On. Waiting for a game."
        self.boost_status.setText(text)

    def refresh_tuneup(self):
        clear_layout(self.tune_box)
        items = core.tuneup_items()
        for it in items:
            row = QFrame()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 4, 0, 4)
            h.setSpacing(12)
            text, state = TUNE_PILLS[it["state"]]
            pill = label("", "pill")
            set_pill(pill, text, state)
            pill.setFixedWidth(64)
            pill.setAlignment(Qt.AlignCenter)
            h.addWidget(pill, 0, Qt.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(label(it["title"], "cardTitle"))
            col.addWidget(label(it["desc"] if it["state"] != "na" else
                                "Your SteamOS kernel doesn't have this one, so it's skipped.", "cardDesc", wrap=True))
            h.addLayout(col, 1)
            self.tune_box.addWidget(row)
        applied = core.tuneup_applied()
        supported = any(i["state"] != "na" for i in items)
        partly = applied and any(i["state"] == "off" for i in items)
        self.btn_tune.setText("Apply again" if partly else "✔ Applied" if applied else "Apply tune-up")
        self.btn_tune.setEnabled(supported and (not applied or partly))
        self.btn_untune.setEnabled(applied)

    # ---- actions ----
    def set_game_env(self, key: str, on: bool):
        if self._loading:
            return
        core.game_env_set(key, bool(on))
        self.refresh_game_env()
        if on:
            self.hub.toast("Saved. Restart the handheld to apply it to games.")

    def set_boost(self, on):
        if self._loading:
            return
        update_config(lambda c: c.setdefault("performance", {}).__setitem__("boost", bool(on)))
        if on:
            if not load_config()["agent"].get("enabled") or not core.agent_running():
                self.hub.enable_agent()
            if core.boost_backend() == "epp" and not core.epp_writable():
                self.allow_boost()
        self.refresh_boost()

    def allow_boost(self):
        if self.hub.needs_password():
            return
        cmd = core.boost_permission_cmd()
        if cmd:
            self.hub.runner.submit("Allow Game Boost", cmd, "boost-perms")

    def apply_tuneup(self):
        if self.hub.needs_password():
            return
        items = [i for i in core.tuneup_items() if i["state"] != "na"]
        names = "\n".join(f"• {i['title']}" for i in items)
        if not ask(self, f"Apply the tune-up?\n\n{names}\n\nIt asks for your password once and works "
                         "right away. Undo all puts everything back."):
            return
        if not core.tuneup_applied():      # keep the original values, not already-tuned ones
            core.write_json(core.TUNEUP_BEFORE, core.tuneup_snapshot())
        cmd = core.tuneup_apply_cmd()
        if cmd:
            self.hub.runner.submit("Apply tune-up", cmd, "tuneup")

    def undo_tuneup(self):
        if self.hub.needs_password():
            return
        if not ask(self, "Undo the tune-up and go back to SteamOS's own settings?"):
            return
        before = core.read_json(core.TUNEUP_BEFORE, {}) or {}
        self.hub.runner.submit("Undo tune-up", core.tuneup_undo_cmd(before), "tuneup-undo")

    def job_done(self, key: str, ok: bool):
        if key == "tuneup-undo" and ok:
            core.TUNEUP_BEFORE.unlink(missing_ok=True)
        self.refresh()


class DoctorPage(QWidget):
    """Home > Overview's Checkup since 1.4.0 (it was the Ally Doctor page): only problems show, with their fix;
    everything that's fine folds into one line."""

    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        card, cv = titled_card("stethoscope", "#22c55e", "Checkup")
        self.summary = label("Checking…", "cardDesc", wrap=True)
        cv.addWidget(self.summary)
        self.box = QVBoxLayout()
        self.box.setSpacing(8)
        cv.addLayout(self.box)
        row = QHBoxLayout()
        self.btn_fix_all = button("Fix everything", self.fix_all, "primary")
        row.addWidget(self.btn_fix_all)
        row.addWidget(button("Check again", self.run_checks))
        self.btn_all = button("Show all checks", self.toggle_all)
        row.addWidget(self.btn_all)
        row.addStretch()
        cv.addLayout(row)
        self.block = card
        self.fixes = []
        self.ran = False
        self.show_all = False

    def toggle_all(self, *_args):
        self.show_all = not self.show_all
        self.btn_all.setText("Only problems" if self.show_all else "Show all checks")
        self.show_results(getattr(self, "probe", None))       # just a different view: no new checks

    def check_list(self) -> list:
        h = self.hub
        st = h.state
        cfg = load_config()
        out = []

        def add(status, title, detail, fix_label=None, fix=None, auto=True):
            out.append(dict(status=status, title=title, detail=detail,
                            fix_label=fix_label, fix=fix, auto=auto))

        probe = getattr(self, "probe", None) or {}
        pw = st.get("password")
        add("ok" if pw else "fail" if pw is False else "warn", "Sudo password",
            "Set." if pw else "Not set. Decky, plugins and system tweaks need one.",
            None if pw else "Set password", None if pw else h.set_password, False)

        decky = CATALOG_BY_ID["decky"].check(st)
        expected = cfg["guardian"].get("decky_expected")
        if decky:
            active = core.service_active("plugin_loader")
            add("ok" if active else "fail", "Decky Loader",
                "Installed and running." if active else "Installed but not running.",
                None if active else "Restart Decky",
                None if active else lambda: h.runner.submit(
                    "Restart Decky", "sudo systemctl restart plugin_loader", "decky-restart"))
        else:
            add("fail" if expected else "warn", "Decky Loader",
                "Missing. A SteamOS update probably removed it." if expected else "Not installed.",
                "Repair" if expected else "Install", lambda: h.on_item_action("decky", "install"), expected)

        net = probe.get("net")             # None: the check itself didn't finish, so say so instead of "fine"
        add("ok" if net else "warn" if net is None else "fail", "Internet",
            "Connected." if net else "Couldn't check." if net is None else
            "No connection. Installs and the plugin store won't work.")

        ratio = core.disk_free_ratio(str(HOME))
        add("ok" if ratio > 0.2 else "warn" if ratio > 0.1 else "fail", "Storage space",
            f"{core.disk_usage(str(HOME))}.",
            None if ratio > 0.2 else "Open Storage", None if ratio > 0.2 else lambda: h.go("Storage"), False)

        if probe.get("shader") is not None:
            size = probe["shader"]
            big = size > 5 * 1024 ** 3
            add("warn" if big else "ok", "Shader cache", f"{core.human_size(size)}."
                + (" Clearing it frees space; Steam rebuilds what it needs." if big else ""),
                "Clear" if big else None, h.system.clear_shaders if big else None, False)

        b = core.battery_info()
        if b.get("health"):
            add("ok" if b["health"] >= 80 else "warn", "Battery health",
                f"{b['health']}% of original capacity"
                + (f", {b['cycles']} cycles." if b.get("cycles") else "."))
        if b.get("limit_file"):
            lim = b.get("limit") or "100"
            add("ok" if lim != "100" else "warn", "Charge limit",
                f"Stops at {lim}%." if lim != "100" else
                "No limit set. An 80% limit greatly extends battery lifespan.",
                None if lim != "100" else "Set it", None if lim != "100" else lambda: h.go("Battery & sleep"),
                False)

        leds = [] if core.lighting_shelved() else core.find_leds()
        if leds:
            ok = core.lighting_access_ok(leds)
            add("ok" if ok else "warn", "Lighting permissions",
                "Lighting can change without a password." if ok else
                "Every color change asks for your password, and the background helper can't change the lights.",
                None if ok else "Fix", None if ok else h.enable_led_permissions)

        if cfg["agent"].get("enabled"):
            ok = core.agent_running()
            add("ok" if ok else "fail", "Background helper", "Running." if ok else "Turned on but not running.",
                None if ok else "Restart", None if ok else h.enable_agent)

        has_flathub = probe.get("flathub", True) is not False
        add("ok" if has_flathub else "warn", "Flathub",
            "Available." if has_flathub else "Flathub isn't set up; app installs will add it.",
            "Repair Flatpak", lambda: h.runner.submit(
                "Repair Flatpak", "flatpak repair --user; flatpak update --user -y --noninteractive",
                "flatpak-repair"), False)

        perf = cfg.get("performance") or {}
        if perf.get("boost") and core.boost_backend() == "epp" and not core.epp_writable():
            add("warn", "Game Boost", "On, but it isn't allowed to change the CPU setting yet.",
                "Allow", h.performance.allow_boost)
        if core.tuneup_applied():
            off = [i["title"] for i in core.tuneup_items() if i["state"] == "off"]
            add("warn" if off else "ok", "Tune-up",
                f"Applied, but these aren't active: {', '.join(off)}." if off else "Applied.",
                "Apply again" if off else None, h.performance.apply_tuneup if off else None, False)

        for a in core.read_json(core.DATA_DIR / "alerts.json", []) or []:
            add("warn", "Update Guardian", a.get("text", ""), "Dismiss",
                lambda _=False, i=a.get("id"): h.dismiss_alert(i), False)
        return out

    @staticmethod
    def _probe() -> dict:
        """The slow checks (network, walking the shader cache, flatpak), run off the UI thread."""
        return {"net": core.internet_ok(),
                "shader": core.dir_size(core.SHADER_CACHE) if core.SHADER_CACHE.exists() else None,
                "flathub": "flathub" in core.run_quiet(["flatpak", "remotes", "--columns=name"])[1].split()}

    def run_checks(self, *_args):
        self.ran = True
        if getattr(self, "_probing", False):
            return
        self._probing = True
        self.summary.setText("Checking…")
        BackgroundTask(self, self._probe, self.show_results)

    def show_results(self, probe=None):
        self._probing = False
        self.probe = probe if isinstance(probe, dict) and "error" not in probe else {}
        clear_layout(self.box)
        self.fixes = []
        icons = {"ok": ("✔", "on"), "warn": ("!", "warn"), "fail": ("✖", "fail")}
        problems = 0
        checks = self.check_list()
        for c in checks:
            if c["status"] != "ok":
                problems += 1
                if c["fix"] and c["auto"]:
                    self.fixes.append(c["fix"])
            if c["status"] == "ok" and not self.show_all:
                continue
            card = QWidget()
            h = QHBoxLayout(card)
            h.setContentsMargins(0, 4, 0, 4)
            ic, state = icons[c["status"]]
            pill = label(ic, "pill")
            set_pill(pill, ic, state)
            pill.setFixedWidth(40)
            pill.setAlignment(Qt.AlignCenter)
            h.addWidget(pill)
            tv = QVBoxLayout()
            tv.addWidget(label(c["title"], "cardTitle"))
            tv.addWidget(label(c["detail"], "cardDesc", wrap=True))
            h.addLayout(tv, 1)
            if c["fix"]:
                h.addWidget(button(c["fix_label"], c["fix"],
                                   "primary" if c["status"] == "fail" else ""))
            self.box.addWidget(card)
        self.summary.setText(f"✔ Everything looks good ({len(checks)} checks)." if problems == 0 else
                             f"{problems} thing{'s' if problems != 1 else ''} to look at.")
        self.btn_fix_all.setVisible(bool(self.fixes))

    def fix_all(self, *_args):
        for f in self.fixes:
            f()
        self.fixes = []
        self.btn_fix_all.setVisible(False)


# ==========================================================================
# System
# ==========================================================================

class SystemPage(QWidget):
    """Not a page since 1.4.0: it builds blocks that other sections show (battery card under Battery & sleep,
    storage tools under Storage, profile and settings backup under Backups, SSH under Connections, boot video
    under Theme) and keeps their logic."""

    def __init__(self, hub):
        super().__init__()
        self.hub = hub

        bat, bv = titled_card("battery-charging", "#22c55e", "Battery care")
        self.bat_stats = label("", "cardDesc", wrap=True)
        bv.addWidget(self.bat_stats)
        bv.addWidget(label("Charge limit: stopping at 80% while plugged in greatly extends "
                           "battery lifespan. Kept across reboots.", "cardDesc", wrap=True))
        lr = QHBoxLayout()
        self.limit_box = QComboBox()
        self.limit_box.addItems(["60%", "70%", "80%", "90%", "100% (no limit)"])
        lr.addWidget(self.limit_box)
        self.btn_limit = button("Apply limit", self.apply_limit, "primary")
        lr.addWidget(self.btn_limit)
        lr.addStretch()
        bv.addLayout(lr)
        self.card_battery = bat

        sto, sv = titled_card("hard-drive", "#0ea5e9", "SD card and shader cache")
        self.storage_stats = label("", "cardDesc", wrap=True)
        sv.addWidget(self.storage_stats)
        sr = QHBoxLayout()
        sr.addWidget(button("Clear shader cache", self.clear_shaders))
        self.btn_sd = button("Let apps see the SD card", self.toggle_sd)
        sr.addWidget(self.btn_sd)
        sr.addStretch()
        sv.addLayout(sr)
        self.card_storage = sto

        prof, pv = titled_card("file-down", "#f59e0b", "Your setup in one file",
                               "Export every app, Decky plugin, theme, lighting and automation "
                               "setting. After a SteamOS reinstall, import it to rebuild everything.")
        pr = QHBoxLayout()
        pr.addWidget(button("Export profile", self.export_profile, "primary"))
        pr.addWidget(button("Import profile…", self.import_profile))
        pr.addStretch()
        pv.addLayout(pr)
        self.card_profile = prof

        ssh, shv = titled_card("terminal", "#64748b", "Remote access (SSH)")
        self.ssh_stats = label("", "cardDesc", wrap=True)
        shv.addWidget(self.ssh_stats)
        self.btn_ssh = button("", self.toggle_ssh)
        shv.addWidget(self.btn_ssh, 0, Qt.AlignLeft)
        self.card_ssh = ssh

        boot, btv = titled_card("clapperboard", "#f472b6", "Custom boot video",
                                "Replace Steam's startup animation with any .webm video. "
                                "Tons of free ones on steamdeckrepo.com.")
        self.boot_stats = label("", "cardMeta", wrap=True)
        btv.addWidget(self.boot_stats)
        br = QHBoxLayout()
        br.addWidget(button("Choose video…", self.choose_boot_video, "primary"))
        self.btn_boot_reset = button("Restore default", self.reset_boot_video)
        br.addWidget(self.btn_boot_reset)
        br.addStretch()
        btv.addLayout(br)
        self.card_boot = boot

        bk, bkv = titled_card("archive", "#a855f7", "Back up settings",
                              "Saves Decky plugin settings, Ally Hub settings and MangoHud config into "
                              "~/AllyHub-Backups/auto, no password needed. Update Guardian also does this daily.")
        bkr = QHBoxLayout()
        bkr.addWidget(button("Back up now", self.backup, "primary"))
        bkr.addWidget(button("Open folder", lambda: hub.launch(
            f"mkdir -p {shlex.quote(str(core.SETTINGS_SNAP_DIR))} && xdg-open {shlex.quote(str(core.SETTINGS_SNAP_DIR))}")))
        bkr.addStretch()
        bkv.addLayout(bkr)
        self.card_backup = bk
        self.shader_proc = None
        self.storage_lines = []

    def refresh(self):
        b = core.battery_info()
        parts = []
        if b.get("capacity"):
            parts.append(f"Charge {b['capacity']}% ({b.get('status', '').lower()})")
        if b.get("health"):
            parts.append(f"Health {b['health']}% of design capacity")
        if b.get("cycles"):
            parts.append(f"{b['cycles']} charge cycles")
        self.bat_stats.setText(" · ".join(parts) or "No battery info found.")
        if b.get("limit_file"):
            cur = b.get("limit") or "100"
            self.limit_box.setCurrentIndex({"60": 0, "70": 1, "80": 2, "90": 3}.get(cur, 4))
            self.limit_box.setEnabled(True)
            self.btn_limit.setEnabled(True)
        else:
            self.limit_box.setEnabled(False)
            self.btn_limit.setEnabled(False)
            self.btn_limit.setToolTip("This kernel doesn't expose a charge limit. "
                                      "Ally Center's charge limit may still work.")
        lines = [f"Internal: {core.disk_usage(str(HOME))}"]
        for card in core.sd_cards():
            lines.append(f"{card.name}: {core.disk_usage(str(card))}")
        lines.append("Shader cache: calculating…" if core.SHADER_CACHE.exists() else "Shader cache: empty")
        self.storage_lines = lines
        self.storage_stats.setText("\n".join(lines))
        if core.SHADER_CACHE.exists() and self.shader_proc is None:
            self.shader_proc = QProcess(self)
            self.shader_proc.finished.connect(self._shader_done)
            self.shader_proc.start("du", ["-sb", str(core.SHADER_CACHE)])
        sd = core.flatpak_sd_access()
        self.btn_sd.setText("✔ Apps can see the SD card" if sd else "Let apps see the SD card")
        self.btn_sd.setEnabled(not sd)
        if core.sshd_active():
            where = ", ".join(f"ssh {USER}@{ip}" for ip in core.local_ips()) or "no network yet"
            self.ssh_stats.setText(f"SSH is ON. Connect with: {where}")
            self.btn_ssh.setText("Turn SSH off")
            self.btn_ssh.setObjectName("danger")
        else:
            self.ssh_stats.setText("Turn on SSH to copy files or run commands from your PC "
                                   "(WinSCP, FileZilla). Logs in with your sudo password.")
            self.btn_ssh.setText("Turn SSH on")
            self.btn_ssh.setObjectName("primary")
        repolish(self.btn_ssh)
        if core.BOOT_VIDEO.exists():
            self.boot_stats.setText(f"Custom video active ({core.human_size(core.BOOT_VIDEO.stat().st_size)})")
            self.btn_boot_reset.setEnabled(True)
        else:
            self.boot_stats.setText("Using the default animation.")
            self.btn_boot_reset.setEnabled(False)

    def _shader_done(self, *_):
        out = bytes(self.shader_proc.readAllStandardOutput()).decode().split()
        size = core.human_size(int(out[0])) if out and out[0].isdigit() else "?"
        if self.storage_lines:
            self.storage_lines[-1] = f"Shader cache: {size}"
            self.storage_stats.setText("\n".join(self.storage_lines))
        self.shader_proc.deleteLater()
        self.shader_proc = None

    def charge_limit_cmd(self, value: str) -> Optional[str]:
        b = core.battery_info()
        if not b.get("limit_file"):
            return None
        path = shlex.quote(str(b["limit_file"]))
        bat = Path(b["path"]).name
        value = core.charge_limit_ok(value)
        if not value or '"' in bat or "'" in bat:
            return None
        if value == "100":
            return (f"echo 100 | sudo tee {path} >/dev/null && sudo rm -f {core.UDEV_CHARGE_RULE} && "
                    "echo 'Charge limit removed.'")
        rule = (f'ACTION=="add", SUBSYSTEM=="power_supply", KERNEL=="{bat}", '
                f'ATTR{{charge_control_end_threshold}}="{value}"')
        return (f"echo {value} | sudo tee {path} >/dev/null && "
                f"echo {shlex.quote(rule)} | sudo tee {core.UDEV_CHARGE_RULE} >/dev/null && "
                f"echo 'Battery will stop charging at {value}%.'")

    def apply_limit(self):
        if self.hub.needs_password():
            return
        value = self.limit_box.currentText().split("%")[0]
        cmd = self.charge_limit_cmd(value)
        if cmd:
            self.hub.runner.submit(f"Set charge limit {value}%", cmd, "charge-limit")

    def clear_shaders(self):
        if not ask(self, "Delete Steam's shader cache?\n\nSteam rebuilds it automatically, so the "
                         "first launch of each game may stutter briefly. Close games first."):
            return
        self.hub.runner.submit("Clear shader cache",
                               f"rm -rf {shlex.quote(str(core.SHADER_CACHE))}/* && echo 'Shader cache cleared.'",
                               "shader")

    def toggle_sd(self):
        self.hub.runner.submit("Give apps SD card access",
                               "flatpak override --user --filesystem=/run/media && "
                               "echo 'Flatpak apps can now see your SD card.'", "sd")

    def toggle_ssh(self):
        if self.hub.needs_password():
            return
        on = not core.sshd_active()
        self.hub.runner.submit(f"Turn SSH {'on' if on else 'off'}",
                               f"sudo systemctl {'enable' if on else 'disable'} --now sshd", "ssh")

    def choose_boot_video(self):
        path, _ = QFileDialog.getOpenFileName(self.hub, "Choose a boot video", str(HOME / "Downloads"),
                                              "WebM video (*.webm)", options=file_dialog_options())
        if not path:
            return
        core.BOOT_VIDEO.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, core.BOOT_VIDEO)
        self.hub.toast("Boot video set. You'll see it next time Steam starts.")
        self.refresh()

    def reset_boot_video(self):
        core.BOOT_VIDEO.unlink(missing_ok=True)
        self.hub.toast("Default boot animation restored")
        self.refresh()

    def backup(self):
        """No password: what can be read as you (the same backup Update Guardian makes daily)."""
        try:
            out = core.snapshot_settings()
        except OSError as e:
            msg_warn(self, APP_NAME, f"Couldn't save the backup: {e}")
            return
        self.hub.toast(f"Saved {out.name} (the last 5 are kept)")

    def export_profile(self):
        path = core.export_profile(self.hub.state)
        msg_info(self, APP_NAME, f"Saved your setup to:\n{path}\n\n"
                                "Copy it somewhere safe (SD card, cloud, PC).")

    def import_profile(self):
        """Pick from the profiles in ~/AllyHub-Backups with the controller; any other file is one step further."""
        found = sorted(core.BACKUP_DIR.glob("*.allyhub.json"), reverse=True)[:8] if core.BACKUP_DIR.exists() else []
        other = "Another file…"
        path = ""
        if found:
            pick, ok = ask_item(self, "Import a profile", "Which profile?", [p.name for p in found] + [other])
            if not ok:
                return
            path = str(core.BACKUP_DIR / pick) if pick != other else ""
        if not path:
            path, _ = QFileDialog.getOpenFileName(self.hub, "Import an Ally Hub profile", str(core.BACKUP_DIR),
                                                  "Ally Hub profile (*.allyhub.json *.json)",
                                                  options=file_dialog_options())
        if not path:
            return
        prof = core.read_json(Path(path))
        if not isinstance(prof, dict) or not prof.get("allyhub_profile"):
            msg_warn(self, APP_NAME, "That file isn't an Ally Hub profile.")
            return
        self.hub.import_profile(prof)


# ==========================================================================
# Appearance
# ==========================================================================

class AppearancePage(QWidget):
    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        v = page_shell(self, "Appearance", "Make Ally Hub yours: theme, accent colors, text size "
                                           "and controller navigation.")
        v.addWidget(label("THEME", "section"))
        grid = QGridLayout()
        grid.setSpacing(14)
        self.theme_btns = {}
        for n, (name, p) in enumerate(core.THEMES.items()):
            b = CardButton(116, 140)       # 70 preview + ~40 name + borders
            b.setObjectName("themeCard")
            b.setCheckable(True)
            lay = QVBoxLayout(b)
            lay.setContentsMargins(0, 0, 0, 0)
            prev = QLabel()
            prev.setMinimumHeight(70)
            prev.setAttribute(Qt.WA_TransparentForMouseEvents)
            prev.setStyleSheet(
                f"border-top-left-radius: 14px; border-top-right-radius: 14px;"
                f"background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {p['bg']}, stop:0.45 {p['surface']},"
                f" stop:0.46 {p['accent']}, stop:1 {p['accent2']});")
            lay.addWidget(prev)
            nm = QLabel(name)
            nm.setAttribute(Qt.WA_TransparentForMouseEvents)
            nm.setStyleSheet(f"background: {p['surface']}; color: {p['text']}; padding: 8px 12px;"
                             "border-bottom-left-radius: 14px; border-bottom-right-radius: 14px;"
                             "font-weight: 700;")
            lay.addWidget(nm)
            b.clicked.connect(lambda _=False, t=name: self.set_preset(t))
            self.theme_btns[name] = b
            grid.addWidget(b, n // 4, n % 4)
        v.addLayout(grid)

        v.addWidget(label("ACCENT COLORS", "section"))
        ar = QHBoxLayout()
        self.btn_a1 = button("Accent 1…", lambda: self.pick_accent("accent"))
        self.btn_a2 = button("Accent 2…", lambda: self.pick_accent("accent2"))
        ar.addWidget(self.btn_a1)
        ar.addWidget(self.btn_a2)
        ar.addWidget(button("Match my RGB lighting", self.match_rgb))
        ar.addWidget(button("Reset accents", self.reset_accents))
        ar.addStretch()
        v.addLayout(ar)

        v.addWidget(label("INTERFACE SIZE", "section"))
        v.addWidget(label(f"These sizes are for {'Game Mode' if GAMEMODE else 'Desktop Mode'}. "
                          f"{'Desktop Mode' if GAMEMODE else 'Game Mode'} remembers its own, so switching between "
                          "them never changes your setup.", "cardMeta", wrap=True))
        ir = QHBoxLayout()
        self.ui_size = QComboBox()
        self.ui_sizes = [("auto", "")] + [(f, f"{int(f * 100)}%") for f in (1.0, 1.25, 1.5, 1.75, 2.0)]
        self.ui_size.addItems([f"Auto ({int(core.auto_ui_scale(GAMEMODE) * 100)}%)"] + [t for _, t in self.ui_sizes[1:]])
        self.ui_size.activated.connect(self.save_ui_size)
        ir.addWidget(self.ui_size)
        self.ui_note = label("Scales everything to fit your screen.", "cardDesc", wrap=True)
        ir.addWidget(self.ui_note, 1)
        self.btn_ui_restart = button("Restart to apply", hub.restart_app, "primary")
        self.btn_ui_restart.hide()
        ir.addWidget(self.btn_ui_restart)
        v.addLayout(ir)

        v.addWidget(label("TEXT SIZE", "section"))
        sr = QHBoxLayout()
        self.scale = QSlider(Qt.Horizontal)
        self.scale.setRange(85, 160)
        self.scale.setSingleStep(5)
        self.scale_lbl = label("", "statValue")
        self.scale.valueChanged.connect(lambda val: self.scale_lbl.setText(f"{val}%"))
        self.scale.sliderReleased.connect(self.save_scale)
        sr.addWidget(self.scale, 1)
        sr.addWidget(self.scale_lbl)
        sr.addWidget(button("Apply", self.save_scale))
        v.addLayout(sr)

        v.addWidget(label("LAYOUT", "section"))
        lr = QHBoxLayout()
        self.bars_mode = QComboBox()
        self.bars_mode.addItems(["Header and footer: top and bottom", "Header and footer: on the sides"])
        self.bars_mode.activated.connect(self.save_bars)
        lr.addWidget(self.bars_mode)
        lr.addWidget(label("On the sides gives pages more height, handy with a bigger interface size or on "
                           "a wide screen. Tabs go down the left, status and buttons down the right.",
                           "cardDesc", wrap=True), 1)
        v.addLayout(lr)
        self.footer_cb = QCheckBox("Show the bottom bar (status, button hints, refresh and log)")
        self.footer_cb.toggled.connect(self.save_footer)
        v.addWidget(self.footer_cb)

        v.addWidget(label("CONTROLLER NAVIGATION", "section"))
        cr = QHBoxLayout()
        self.nav_mode = QComboBox()
        self.nav_mode.addItems(["Auto (Game Mode only)", "Always on", "Off"])
        self.nav_mode.activated.connect(self.save_nav)
        self.nav_mode.setProperty("padCycle", False)      # stepping to "Off" would strand the controller
        cr.addWidget(self.nav_mode)
        cr.addWidget(label("D-pad/stick moves, A selects, B goes back, LB/RB switch tabs, LT/RT switch "
                           "sections, X searches plugins, Y refreshes, Menu opens the Steam keyboard.",
                           "cardDesc", wrap=True), 1)
        v.addLayout(cr)
        v.addStretch()

    def refresh(self):
        t = load_config()["theme"]
        for name, b in self.theme_btns.items():
            b.setChecked(name == t.get("preset"))
        pal = core.theme_palette(t)
        for b, key in ((self.btn_a1, "accent"), (self.btn_a2, "accent2")):
            b.setStyleSheet(f"QPushButton {{ border-left: 14px solid {pal[key]}; }}")
        self.scale.setValue(int(core.theme_size(t, "scale", GAMEMODE) or 100))
        cur = core.theme_size(t, "ui_scale", GAMEMODE)
        idx = next((i for i, (v, _) in enumerate(self.ui_sizes) if v == cur), 0)
        self.ui_size.setCurrentIndex(idx)
        self.scale_lbl.setText(f"{self.scale.value()}%")
        self.nav_mode.setCurrentIndex({"auto": 0, "on": 1, "off": 2}.get(t.get("controller_nav"), 0))
        self.bars_mode.setCurrentIndex(1 if t.get("bars") == "sides" else 0)
        self._footer_loading = True
        self.footer_cb.setChecked(bool(t.get("footer", False)))
        self._footer_loading = False

    def _save(self, **kw):
        update_config(lambda c: c["theme"].update(kw))
        self.hub.apply_theme()
        self.refresh()

    def set_preset(self, name):
        self._save(preset=name, accent=None, accent2=None)

    def pick_accent(self, key):
        cur = core.theme_palette(load_config()["theme"])[key]
        c = ask_color(QColor(cur), self, "Pick an accent color")
        if c.isValid():
            self._save(**{key: c.name()})

    def match_rgb(self):
        rgb = load_config().get("rgb")
        if not rgb:
            self.hub.toast("Set a lighting color first")
            return
        c = QColor(*rgb["rgb"])
        self._save(accent=c.name(), accent2=c.lighter(140).name())

    def reset_accents(self):
        self._save(accent=None, accent2=None)

    def save_ui_size(self, idx):
        val = self.ui_sizes[idx][0]
        update_config(lambda c: c["theme"].__setitem__(f"ui_scale_{core.mode_key(GAMEMODE)}", val))
        self.btn_ui_restart.show()
        self.ui_note.setText("Restart Ally Hub to apply the new size.")

    def save_scale(self):
        self._save(**{f"scale_{core.mode_key(GAMEMODE)}": self.scale.value()})

    def save_nav(self, idx):
        self._save(controller_nav=["auto", "on", "off"][idx])

    def save_footer(self, on):
        if getattr(self, "_footer_loading", False):
            return
        update_config(lambda c: c["theme"].update(footer=bool(on)))
        try:
            self.hub.arrange_bars(self.hub.bars)
        except Exception:
            core.report_exception("gui-layout")
        self.hub.apply_theme()

    def save_bars(self, idx):
        mode = "sides" if idx == 1 else "top"
        try:
            self.hub.arrange_bars(mode)
            update_config(lambda c: c["theme"].update(bars=mode))
        except Exception:                                   # never crash the app over a layout switch
            core.report_exception("gui-layout")
            update_config(lambda c: c["theme"].update(bars="top"))
            msg_info(self, APP_NAME, "That layout couldn't be applied, so Ally Hub stays on top "
                                                    "and bottom. It's been reported.")
        self.hub.apply_theme()
        self.refresh()



# ==========================================================================
# Updates & error reports
# ==========================================================================

class BackgroundTask(QObject):
    """Runs a blocking function on a thread and hands the result back on the UI thread."""
    done = Signal(object)

    def __init__(self, parent, fn, callback):
        super().__init__(parent)
        self.done.connect(callback)
        import threading
        threading.Thread(target=lambda: self.done.emit(self._safe(fn)), daemon=True).start()

    @staticmethod
    def _safe(fn):
        try:
            return fn()
        except Exception as e:
            core.report_exception("gui-background")
            return {"error": str(e)}


IGNORABLE_FAILURES = re.compile(
    r"incorrect password|no password was provided|a password is required|askpass|"
    r"could not resolve host|network is unreachable|temporary failure in name resolution|"
    r"connection timed out|no space left", re.I)


class UpdatesPage(QWidget):
    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        v = page_shell(self, "Updates & Reports",
                       "Ally Hub keeps itself up to date and can report its own errors so they get "
                       "fixed automatically.")
        self.testing_banner = QFrame()            # the owner's call: test builds come with a clear way out
        self.testing_banner.setObjectName("banner")
        tbl = QHBoxLayout(self.testing_banner)
        tbl.setContentsMargins(20, 12, 20, 12)
        tbl.addWidget(label("You're on test builds. If one ever won't open, use \"Ally Hub Testing Rescue\" in "
                            "your app menu (Desktop Mode) to roll back or go back to Stable. If that fails too, "
                            "uninstall Ally Hub and install it again.", "bannerText", wrap=True), 1)
        v.addWidget(self.testing_banner)
        self.rollback_banner = QFrame()
        self.rollback_banner.setObjectName("banner")
        rbl = QHBoxLayout(self.rollback_banner)
        rbl.setContentsMargins(20, 12, 20, 12)
        self.rollback_text = label("", "bannerText", wrap=True)
        rbl.addWidget(self.rollback_text, 1)
        rbl.addWidget(button("OK", self.ack_rollback))
        v.addWidget(self.rollback_banner)

        grid = two_col_grid()
        ucard, uv = titled_card("refresh-cw", "#22c55e", "Auto-update")
        self.ver_label = label("", "bigValue")
        uv.addWidget(self.ver_label)
        self.update_info = label("", "cardDesc", wrap=True)
        uv.addWidget(self.update_info)
        self.auto_cb = QCheckBox("Install updates automatically (checks every 6 hours)")
        self.auto_cb.toggled.connect(lambda on: update_config(
            lambda c: c["updates"].__setitem__("auto_update", on)))
        uv.addWidget(self.auto_cb)
        chr_ = QHBoxLayout()
        chr_.addWidget(label("Update channel", "cardDesc"))
        self.channel = QComboBox()
        self.channel.addItem("Stable", "stable")
        self.channel.addItem("Testing (new features first, may have bugs)", "testing")
        self.channel.setProperty("padCycle", False)       # a channel change needs A + a confirmation
        self.channel.currentIndexChanged.connect(self.change_channel)
        chr_.addWidget(self.channel, 1)
        uv.addLayout(chr_)
        ur = QHBoxLayout()
        self.btn_check = button("Check now", self.check_now, "primary")
        self.btn_rollback = button("Roll back", self.do_rollback, "danger")
        self.btn_restart = button("Restart Ally Hub", hub.restart_app, "primary")
        ur.addWidget(self.btn_check)
        ur.addWidget(self.btn_restart)
        ur.addWidget(self.btn_rollback)
        ur.addStretch()
        uv.addLayout(ur)
        uv.addWidget(label("If a new version fails to start, Ally Hub automatically goes back to the "
                           "previous one and reports the problem.", "cardMeta", wrap=True))
        uv.addStretch()
        grid.addWidget(ucard, 0, 0)

        rcard, rv = titled_card("bug", "#e11d48", "Error reports",
                                "When something breaks, Ally Hub files a GitHub issue in the project "
                                "repository. Fixes go out with the next update. Personal details "
                                "(IP and MAC addresses, your username, PIN and keys) are removed first. "
                                "Reports are public.")
        self.report_cb = QCheckBox("Send error reports")
        self.report_cb.toggled.connect(self.toggle_reporting)
        rv.addWidget(self.report_cb)
        self.token = QLineEdit()
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("GitHub access key (github_pat_…)")
        tr = QHBoxLayout()
        tr.addWidget(self.token, 1)
        tr.addWidget(button("Save key", self.save_token))
        rv.addLayout(tr)
        self.report_info = label("", "cardMeta", wrap=True)
        rv.addWidget(self.report_info)
        rr = QHBoxLayout()
        self.btn_test = button("Send a test report", self.send_test)
        rr.addWidget(self.btn_test)
        rr.addWidget(button("View reports", lambda: QDesktopServices.openUrl(
            QUrl(f"https://github.com/{core.repo_name()}/issues"))))
        rr.addStretch()
        rv.addLayout(rr)
        rv.addStretch()
        grid.addWidget(rcard, 0, 1)
        v.addLayout(grid)

        hcard, hv = titled_card("key-round", "#64748b", "Getting a GitHub access key",
                                "Do this once, in Desktop Mode, in a browser where you're signed in "
                                "to GitHub:")
        hv.addWidget(label(
            "1. Open github.com/settings/personal-access-tokens/new\n"
            "2. Name it \"Ally Hub\" and set an expiration (1 year is fine)\n"
            f"3. Repository access: Only select repositories → {core.REPO_DEFAULT}\n"
            "4. Permissions → Repository → Issues: Read and write (nothing else)\n"
            "5. Generate, copy the key, paste it above and tap Save key",
            "cardDesc", wrap=True))
        hv.addWidget(button("Open the GitHub page", lambda: QDesktopServices.openUrl(
            QUrl("https://github.com/settings/personal-access-tokens/new"))), 0, Qt.AlignLeft)
        v.addWidget(hcard)
        self.key_guide = hcard               # only while no key is saved

        # small disclosure (the owner's call): who builds and maintains Ally Hub
        v.addWidget(label("Ally Hub is built and maintained with Claude, Anthropic's AI, under the developer's direction. "
                          "Error reports and daily fixes are handled by Claude.", "cardMeta", wrap=True))
        v.addWidget(label("CHANGELOG", "section"))
        self.changelog = label("", "cardDesc", wrap=True)
        self.changelog.setTextFormat(Qt.MarkdownText)
        cl = card_frame()
        cll = QVBoxLayout(cl)
        cll.setContentsMargins(20, 16, 20, 16)
        cll.addWidget(self.changelog)
        v.addWidget(cl)
        v.addStretch()
        self.installed_new = None

    def refresh(self):
        cfg = load_config()
        st = core.update_state()
        self.key_guide.setVisible(not core.github_token())
        self.testing_banner.setVisible(core.update_channel(cfg) == "testing")
        disk_ver = core.read_text(core.APP_DIR / "VERSION") or VERSION
        self.ver_label.setText(f"Version {core.version_label()}")
        self.channel.blockSignals(True)
        self.channel.setCurrentIndex(1 if core.update_channel(cfg) == "testing" else 0)
        self.channel.blockSignals(False)
        parts = [f"Updates from github.com/{core.repo_name()}"]
        if st.get("last_check"):
            parts.append("last checked " + time.strftime("%b %d %H:%M", time.localtime(st["last_check"])))
        if st.get("last_remote") and core.parse_version(st["last_remote"]) > core.parse_version(VERSION):
            parts.append(f"latest is {core.display_version(st['last_remote'])}")
        if core.on_probation():
            parts.append("this version is new and being checked")
        self.update_info.setText(" · ".join(parts))
        self.btn_restart.setVisible(disk_ver != VERSION)
        if disk_ver != VERSION:
            self.btn_restart.setText(f"Restart to finish updating to {core.display_version(disk_ver)}")
        prev = core.previous_version()
        self.btn_rollback.setVisible(bool(prev) and disk_ver == VERSION)
        self.btn_rollback.setText(f"Roll back to {core.display_version(prev)}" if prev else "Roll back")
        for cb, val in ((self.auto_cb, cfg["updates"].get("auto_update")),
                        (self.report_cb, cfg["updates"].get("reporting"))):
            cb.blockSignals(True)
            cb.setChecked(bool(val))
            cb.blockSignals(False)
        has_tok = bool(core.github_token())
        pending = len(core.pending_reports())
        self.report_info.setText(
            ("✔ Access key saved." if has_tok else "No access key yet, see the steps below.")
            + (f" {pending} report(s) waiting to send." if pending else ""))
        self.btn_test.setEnabled(has_tok)
        rb = st.get("rolled_back")
        self.rollback_banner.setVisible(bool(rb) and not rb.get("ack"))
        if rb:
            self.rollback_text.setText(f"Version {rb.get('from')} had a problem ({rb.get('reason')}), "
                                       f"so Ally Hub went back to {rb.get('to')}. It's been reported.")
        self.changelog.setText(core.changelog_text() or "No release notes yet.")

    def ack_rollback(self):
        st = core.update_state()
        if st.get("rolled_back"):
            st["rolled_back"]["ack"] = True
            core.save_update_state(st)
        self.refresh()

    def toggle_reporting(self, on):
        update_config(lambda c: c["updates"].__setitem__("reporting", on))
        self.refresh()

    def save_token(self):
        t = self.token.text().strip()
        if not t:
            return
        if not re.fullmatch(r"(github_pat_|ghp_)[A-Za-z0-9_]{20,}", t):
            msg_warn(self, APP_NAME, "That doesn't look like a GitHub access key.")
            return
        core.save_github_token(t)
        self.token.clear()
        self.hub.toast("Access key saved")
        self.refresh()

    def check_now(self):
        self.btn_check.setEnabled(False)
        self.hub.toast("Checking for updates…")
        BackgroundTask(self, core.check_for_update, self._checked)

    def _checked(self, res):
        self.btn_check.setEnabled(True)
        if res.get("error"):
            self.hub.toast(res["error"])
        elif not res.get("available"):
            self.hub.toast(f"You're up to date ({core.version_label()})")
        elif ask(self, f"Version {core.display_version(res['remote'])}"
                       f"{' (testing)' if res.get('branch') == 'testing' else ''} is available. Install it now?"):
            self.hub.toast(f"Installing {core.display_version(res['remote'])}…")
            BackgroundTask(self, lambda: core.install_update(res["remote"], res.get("branch", "main")),
                           self._installed)
        self.refresh()

    def change_channel(self, *_args):
        want = self.channel.currentData()
        if not isinstance(want, str) or want == core.update_channel():
            return
        if want == "testing" and not ask(
                self, "Switch to test builds?\n\nYou get new features before everyone else, straight from the "
                      "developer's testing branch. Test builds can break, even badly enough that Ally Hub won't "
                      "open.\n\nIf that happens: open \"Ally Hub Testing Rescue\" from your app menu (Desktop "
                      "Mode) to roll back, go back to Stable, or uninstall. If even that doesn't work, uninstall "
                      "Ally Hub and install it again with the command from the README.\n\nYou can switch back to "
                      "Stable any time."):
            self.refresh()
            return
        update_config(lambda c: c["updates"].__setitem__("channel", want))
        core.app_log("update", f"channel: {want}")
        try:
            core.sync_testing_rescue()            # the rescue entry exists only on Testing
        except Exception:
            core.report_exception("gui-rescue")
        self.refresh()
        self.btn_check.setEnabled(False)
        BackgroundTask(self, core.check_for_update, lambda r: self._channel_checked(want, r))

    def _channel_checked(self, want: str, res):
        self.btn_check.setEnabled(True)
        if not isinstance(res, dict) or res.get("error"):
            self.hub.toast("Channel saved. Ally Hub checks for updates when it's online.")
        elif want == "stable" and res.get("stable") and \
                core.parse_version(res["stable"]) < core.parse_version(VERSION):
            if ask(self, f"You're on a test build ({core.display_version()}). Go back to the stable version "
                         f"{core.display_version(res['stable'])} now?\n\nIf not, you stay on this build until "
                         "a newer stable version comes out."):
                self.hub.toast(f"Installing {core.display_version(res['stable'])}…")
                BackgroundTask(self, lambda: core.install_update(res["stable"], "main", allow_older=True),
                               self._installed)
        elif res.get("available"):
            self._checked(res)
            return
        else:
            self.hub.toast(f"Channel: {'Testing' if want == 'testing' else 'Stable'}. You're up to date.")
        self.refresh()

    def _installed(self, result):
        ok, msg = result if isinstance(result, tuple) else (False, result.get("error", "?"))
        self.hub.toast(msg)
        if not ok:
            core.report_update_failure(msg)
        if ok:
            if core.agent_running():
                self.hub.runner.submit("Restart agent", "systemctl --user restart allyhub-agent.service",
                                       "agent")
            if ask(self, f"{msg}. Restart Ally Hub now?"):
                self.hub.restart_app()
        self.refresh()

    def do_rollback(self):
        prev = core.previous_version()
        if not prev or not ask(self, f"Go back to version {prev}?"):
            return
        ok, msg = core.rollback("rolled back by you", mark_bad=True)
        self.hub.toast(msg)
        if ok:
            if core.agent_running():
                self.hub.runner.submit("Restart agent", "systemctl --user restart allyhub-agent.service",
                                       "agent")
            self.hub.restart_app()

    def send_test(self):
        def job():
            p = core.queue_report("test", "Test report from Ally Hub",
                                  "Error reporting works. You can close this issue.",
                                  core._fingerprint("test", time.time()))
            if p is None:
                return (0, 0, "Reporting is off")
            sent, failed = core.upload_reports()
            return (sent, failed, "")
        self.hub.toast("Sending a test report…")
        BackgroundTask(self, job, lambda r: (self.hub.toast(
            r[2] or ("Test report sent ✔" if r[0] else "Sending failed, check your access key")
            if isinstance(r, tuple) else "Sending failed"), self.refresh()))


# ==========================================================================
# Tweaks + Activity
# ==========================================================================

class TweaksPage(QWidget):
    """Home > Overview's Quick fixes since 1.4.0 (it was Settings > Tweaks). The password and Decky repair live in
    the Checkup when they're needed, so they aren't repeated here."""

    def __init__(self, hub):
        super().__init__()
        self.hub = hub
        card, cv = titled_card("wrench", "#8b5cf6", "Quick fixes", "One tap for the usual SteamOS hiccups.")
        grid = QGridLayout()
        grid.setSpacing(10)
        self.btn_steam = button("Add Ally Hub to Game Mode", hub.add_to_steam)
        self.btn_game_mode = button("Return to Game Mode", hub.return_to_game_mode)
        fixes = [
            button("Update all apps", lambda: hub.runner.submit(
                "Update apps", "flatpak update --user -y --noninteractive; flatpak update -y --noninteractive",
                "flatpak-update")),
            button("Restart Decky", self.restart_decky),
            button("Reinstall Decky", lambda: hub.on_item_action("decky", "install")),
            button("Clean up app leftovers", lambda: hub.runner.submit(
                "Clean up app leftovers", "flatpak uninstall --user --unused -y --noninteractive; "
                                          "flatpak uninstall --unused -y --noninteractive", "flatpak-clean")),
            self.btn_steam,
            self.btn_game_mode,
        ]
        for n, b in enumerate(fixes):
            grid.addWidget(b, n // 3, n % 3)
        cv.addLayout(grid)
        self.block = card

    def restart_decky(self, *_args):
        if self.hub.needs_password():
            return
        self.hub.runner.submit("Restart Decky", "sudo systemctl restart plugin_loader", "decky-restart")

    def refresh(self):
        self.btn_steam.setVisible(not core.in_steam_library())
        self.btn_game_mode.setVisible(not GAMEMODE)


class ActivityPage(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(36, 32, 36, 32)
        v.setSpacing(12)
        v.addWidget(label("Activity", "pageTitle"))
        v.addWidget(label("Live output from installs and tweaks.", "pageSub"))
        self.log = QPlainTextEdit()
        self.log.setObjectName("log")
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        v.addWidget(self.log, 1)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(button("Clear", self.log.clear))
        v.addLayout(row)

    def append(self, text: str):
        self.log.moveCursor(QTextCursor.End)
        self.log.insertPlainText(text)
        self.log.moveCursor(QTextCursor.End)


# ==========================================================================
# Main window
# ==========================================================================

class SectionPage(QWidget):
    """A page that only holds blocks from other objects (Settings > Backups)."""

    def __init__(self, title: str, sub: str, refreshers=()):
        super().__init__()
        page_shell(self, title, sub)
        self._shell.addStretch()
        self.refreshers = list(refreshers)

    def refresh(self):
        for f in self.refreshers:
            f()


class Hub(QMainWindow):
    # (tab, [(section name, attribute)]). 1.4.0 (the owner's call): grouped by what you're doing, few sections per
    # tab, expert controls behind Simple / Advanced. Setup shows as a section only until it's done.
    TABS = [
        ("Home", [("Overview", "health"), ("Battery & sleep", "sleep"), ("Storage", "storage"), ("Setup", "setup")]),
        ("Store", [("Browse", "browse"), ("Launchers", "launchers")]),
        ("Games", [("Game settings", "games"), ("Performance", "performance"), ("Saves", "saves")]),
        ("Customize", [("Lighting", "lighting_section"), ("Theme", "appearance")]),
        ("Settings", [("General", "updates"), ("Connections", "connect_page"), ("Backups", "backups"),
                      ("Activity", "activity")]),
    ]
    # old section names (code paths, earlier docs) still land in the right place
    ALIASES = {"Home": "Overview", "Health": "Overview", "Doctor": "Overview", "Tweaks": "Overview",
               "Sleep": "Battery & sleep", "System": "Battery & sleep", "Mods": "Browse", "Apps": "Browse",
               "Plugin store": "Browse", "Plugin Store": "Browse", "Themes": "Theme", "Appearance": "Theme",
               "Automation": "General", "Updates": "General", "Connect": "Connections", "Games": "Game settings"}
    BROWSE_FILTERS = {"Mods": "mods", "Apps": "apps", "Plugin store": "plugins", "Plugin Store": "plugins"}

    @property
    def PAGE_NAMES(self):
        return [n for _, secs in self.TABS for n, _ in secs]

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle(APP_NAME)
        icon = core.APP_DIR / "allyhub.svg"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        avail = app.primaryScreen().availableGeometry()
        self.resize(min(1280, avail.width()), min(800, avail.height()))
        self.state = {"flatpaks": set(), "decky": {}, "password": None}
        self._pw_term = None            # pid of the terminal running passwd, while it's open
        self._pw_timer = QTimer(self)   # watches that pid: the terminal is detached so closing Ally Hub never kills it
        self._pw_timer.setInterval(1000)
        self._pw_timer.timeout.connect(self._watch_password_window)
        self.installing = set()
        self.runner = JobRunner(write_helpers())
        global _HUB
        _HUB = self
        self._sheet = None
        self._decky_after = {}             # job key -> callback(ok) for Decky on/off jobs
        self.qam_after_decky = False       # setup: add the Quick Access panel once Decky is installed

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        # ---- header: brand · LB [tabs] RB · status (laid out by arrange_bars) ----
        self.top_frame = QFrame()
        self.top_frame.setObjectName("topBar")
        self.brand_badge = brand_icon(38)
        self.brand_label = label(APP_NAME, "brandSmall")
        self.hint_lb = label("LB", "key")
        self.tab_buttons = []
        for i, (name, _secs) in enumerate(self.TABS):
            b = button(name, lambda _=False, i=i: self.set_tab(i), "tab")
            b.setCheckable(True)
            self.tab_buttons.append(b)
        self.hint_rb = label("RB", "key")
        self.top_status = label("", "topStatus")

        # ---- pages ----
        self.store_page = StorePage(self)
        self.browse = BrowsePage(self, self.store_page)
        self.mods = self.apps = self.browse          # older code paths
        self.lighting = LightingPage(self)          # Ally Hub drives the rings (controller "allyhub")
        self.huesync_page = HueSyncPage(self)       # HueSync drives them (controller "huesync", default)
        self.lighting_section = LightingSection(self.lighting, self.huesync_page)
        self.automation = AutomationPage(self)
        self.connect_page = ConnectPage(self)
        self.health = HealthPage(self)
        self.system = SystemPage(self)
        self.performance = PerformancePage(self)
        self.launchers = LaunchersPage(self)
        self.storage = StoragePage(self)
        self.games = GamesPage(self)
        self.saves = SavesPage(self)
        self.sleep = SleepPage(self)
        self.setup = SetupPage(self)
        self.doctor = DoctorPage(self)
        self.appearance = AppearancePage(self)
        self.updates = UpdatesPage(self)
        self.tweaks = TweaksPage(self)
        self.activity = ActivityPage()
        self.backups = SectionPage("Backups", "Your whole setup in one file, and your settings saved daily.",
                                   [self.system.refresh])
        self.compose_sections()
        self.pages = [getattr(self, attr) for _, secs in self.TABS for _, attr in secs]

        self.stack = QStackedWidget()
        self.groups = []
        for _name, secs in self.TABS:
            g = GroupPage(self, [(n, getattr(self, attr)) for n, attr in secs])
            self.groups.append(g)
            self.stack.addWidget(g)

        # ---- footer ----
        self.footer_frame = QFrame()
        self.footer_frame.setObjectName("statusBar")
        self.status = label("Ready", "statusText")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        self.pad_hint = None
        self.btn_refresh = button("⟳ Refresh", self.refresh)
        self.btn_log = button("View log", lambda: self.go("Activity"))
        self.btn_report = button("Report a problem", self.report_problem)
        self.btn_report.setToolTip("Report a problem")
        try:
            self.arrange_bars(load_config()["theme"].get("bars", "top"))
        except Exception:                                   # a bad layout setting must not stop the app
            core.report_exception("gui-layout")
            update_config(lambda c: c["theme"].update(bars="top"))
            self.arrange_bars("top")

        self.runner.output.connect(self.activity.append)
        self.runner.started.connect(self.on_job_started)
        self.runner.finished.connect(self.on_job_finished)
        self.runner.idle.connect(self.on_idle)
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(lambda: self.status.setText("Ready" if self.footer_on else ""))
        self.clock = QTimer(self)
        self.clock.timeout.connect(self.update_top_status)
        self.clock.start(30000)

        self.gamepad = GamepadNav(self)
        self.apply_theme()
        self.apply_mode()
        self.update_setup_chip()
        self.set_tab(0)
        self.focus_tabs()
        self.update_top_status()
        QTimer.singleShot(50, self.refresh)
        QTimer.singleShot(800, self.show_whats_new)
        QTimer.singleShot(3000, self.maybe_check_updates)
        QTimer.singleShot(core.HEALTHY_AFTER_S * 1000, lambda: core.mark_healthy("gui"))

    # ---- sections built from blocks (1.4.0) ----
    def compose_sections(self):
        """Put each block on the page the owner's map gives it. The objects that built the blocks keep their logic
        (self.system, self.automation, self.doctor, self.tweaks); only where the blocks show changed."""
        retitle(self.health, "Overview", "How your handheld is doing, and anything that needs you.")
        self.health._shell.insertWidget(self.health.slot, block(self.doctor.block, self.tweaks.block))
        retitle(self.sleep, "Battery & sleep", "Battery care, and what every sleep cost and what woke the handheld.")
        add_block(self.sleep, self.system.card_battery, 0)
        add_block(self.storage, self.system.card_storage, heading="More")
        add_block(self.saves, self.automation.block_saves, heading="Every game")
        add_block(self.lighting, self.automation.block_lighting)
        retitle(self.store_page, "Decky plugins", "The official Decky plugin store, and every plugin you have.")
        retitle(self.appearance, "Theme", "Colors, sizes, where the bars sit, and Steam's boot video.")
        add_block(self.appearance, self.system.card_boot, heading="Boot video")
        retitle(self.updates, "General", "How much Ally Hub shows, the background helper, and updates.")
        mcard, mv = titled_card("layout-grid", "#0ea5e9", "How much to show",
                                "Simple keeps things calm. Advanced adds the expert controls: system tune-up, "
                                "Proton per game, wake blockers, SSH and the activity log.")
        mr = QHBoxLayout()
        self.mode_box = QComboBox()
        self.mode_box.addItems(["Simple", "Advanced"])
        self.mode_box.setCurrentIndex(1 if advanced_mode() else 0)
        self.mode_box.activated.connect(self.set_mode)
        self.mode_box.setProperty("padCycle", False)      # A opens it; Left/Right just move on
        mr.addWidget(self.mode_box)
        mr.addWidget(button("Run setup again", self.rerun_setup))
        mr.addWidget(button("Activity log", lambda: self.go("Activity")))   # reachable in Simple too
        mr.addStretch()
        mv.addLayout(mr)
        add_block(self.updates, block(mcard, self.automation.block_general), 0)
        retitle(self.connect_page, "Connections", "Wake your PC, play from anywhere, and control your handheld "
                                                  "from your phone.")
        add_block(self.connect_page, adv(self.system.card_ssh))
        for card in (self.system.card_profile, self.system.card_backup):
            add_block(self.backups, card)

    def set_mode(self, i: int):
        update_config(lambda c: c["theme"].__setitem__("advanced", i == 1))
        self.apply_mode()
        self.toast("Advanced: everything shows" if i == 1 else "Simple: the expert controls are tucked away")

    def apply_mode(self):
        on = advanced_mode()
        for box in list(_ADVANCED):
            try:
                box.setVisible(on)
            except RuntimeError:            # its page section was rebuilt
                _ADVANCED.remove(box)
        self.set_section_hidden("Activity", not on)
        if getattr(self, "games", None) is not None and self.current_page() is self.games:
            self.games.refresh()            # the game view is built per game, so it's redrawn

    def set_section_hidden(self, name: str, hidden: bool):
        for ti, (_tab, secs) in enumerate(self.TABS):
            for si, (n, _a) in enumerate(secs):
                if n == name:
                    g = self.groups[ti]
                    g.set_hidden(si, hidden)
                    if hidden and self.tab_index() == ti and g.index == si:
                        g.select(0)

    def update_setup_chip(self):
        done = bool((load_config().get("setup") or {}).get("done", True))
        self.set_section_hidden("Setup", done and self.current_page() is not self.setup)

    def rerun_setup(self, *_args):
        self.setup.step = 0
        self.go("Setup")

    # ---- layout: header and footer at the top and bottom, or on the sides ----
    def arrange_bars(self, mode: str):
        """Lay the header and footer out as rows (top/bottom) or columns (left/right), live.
        Never hand an old layout to a throwaway QWidget: Qt reparents every widget in it, so they would be
        deleted with it. Each arrangement is built in a NEW container widget; the shared widgets are moved
        into it first, and only the then-empty old container is deleted."""
        self.bars = "sides" if mode == "sides" else "top"
        side = self.bars == "sides"
        # the bottom bar is off unless turned on (the owner's call): then status, progress and Report a problem
        # move into the header, and refresh/log live on Y and Settings > Activity
        foot = bool(load_config()["theme"].get("footer", False))
        self.footer_on = foot
        focused = QApplication.focusWidget()          # moving widgets drops focus; put it back after
        old_top, old_foot, old_body = (getattr(self, n, None) for n in ("_top_inner", "_foot_inner", "_body"))
        # sides are icon only (the owner's call): no words, just icons and key caps, names in tooltips
        self.pad_hint = key_hints([(k, "") for k, _ in PAD_KEYS] if side else PAD_KEYS, vertical=side)
        self._label_buttons(side)
        center = Qt.AlignHCenter

        # header
        self._top_inner = QWidget()
        t = QVBoxLayout(self._top_inner) if side else QHBoxLayout(self._top_inner)
        t.setContentsMargins(*((14, 18, 14, 18) if side else (20, 10, 20, 10)))
        t.setSpacing(10)
        for w in (self.brand_badge, self.brand_label):
            t.addWidget(w, 0, center) if side else t.addWidget(w)
        t.addSpacing(12) if side else t.addStretch(1)
        t.addWidget(self.hint_lb, 0, center) if side else t.addWidget(self.hint_lb)
        for b in self.tab_buttons:
            t.addWidget(b)
        t.addWidget(self.hint_rb, 0, center) if side else t.addWidget(self.hint_rb)
        t.addStretch(1)
        if not foot:
            t.addWidget(self.status)                 # always moved (hidden in sides): never left behind
            t.addWidget(self.progress, 0, center) if side else t.addWidget(self.progress)
            t.addWidget(self.btn_report, 0, center) if side else t.addWidget(self.btn_report)
        t.addWidget(self.top_status, 0, center) if side else t.addWidget(self.top_status)

        # footer
        self._foot_inner = QWidget()
        f = QVBoxLayout(self._foot_inner) if side else QHBoxLayout(self._foot_inner)
        f.setContentsMargins(*((14, 18, 14, 18) if side else (20, 8, 20, 8)))
        f.setSpacing(10)
        self.progress.setFixedWidth(64 if side else (200 if foot else 120))
        if foot:
            f.addWidget(self.status, 0 if side else 1)
            f.addWidget(self.progress)
        if side:
            f.addStretch(1)
        f.addWidget(self.pad_hint)
        for w in (self.btn_refresh, self.btn_log) + ((self.btn_report,) if foot else ()):
            f.addWidget(w)

        # the frames keep one fixed layout each that holds the current inner widget
        for frame, inner, old in ((self.top_frame, self._top_inner, old_top),
                                  (self.footer_frame, self._foot_inner, old_foot)):
            if frame.layout() is None:
                fl = QVBoxLayout(frame)
                fl.setContentsMargins(0, 0, 0, 0)
                fl.setSpacing(0)
            frame.layout().addWidget(inner)
            if old is not None:
                frame.layout().removeWidget(old)
                old.hide()
                old.deleteLater()                   # empty now: its widgets moved into the new inner
            # side columns stay narrow (icons only) so the page gets the room; rows fill the width
            frame.setMaximumWidth(96 if side else 16777215)
            frame.setProperty("side", side)
            repolish(frame)

        # body: header, pages and footer in a row (sides) or a column (top/bottom)
        root = self.centralWidget()
        if root.layout() is None:
            rl = QVBoxLayout(root)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(0)
        self._body = QWidget()
        box = QHBoxLayout(self._body) if side else QVBoxLayout(self._body)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)
        box.addWidget(self.top_frame)
        box.addWidget(self.stack, 1)
        box.addWidget(self.footer_frame)
        root.layout().addWidget(self._body)
        if old_body is not None:
            root.layout().removeWidget(old_body)
            old_body.hide()
            old_body.deleteLater()
        # moving a widget can change whether it shows: put back what should be visible right now
        # (the old pad_hint goes with its old container)
        self.progress.setVisible(bool(getattr(self, "runner", None) and self.runner.busy()))
        self.brand_label.setVisible(not side)
        self.status.setVisible(not side)              # the progress bar shows activity in the side column
        self.footer_frame.setVisible(foot)
        if not foot and self.status.text() == "Ready":
            self.status.setText("")
        if hasattr(self, "clock"):
            self.update_top_status()
        if focused is not None:
            QTimer.singleShot(0, lambda w=focused: w.setFocus(Qt.OtherFocusReason))
        if hasattr(self, "gamepad"):
            for w in (self.pad_hint, self.hint_lb, self.hint_rb):
                w.setVisible(self.gamepad.enabled)

    FOOT_BUTTONS = (("btn_refresh", "refresh-cw", "⟳ Refresh", "Refresh"),
                    ("btn_log", "terminal", "View log", "View log"),
                    ("btn_report", "bug", "Report a problem", "Report a problem"))

    def _label_buttons(self, side: bool):
        """Words on the top/bottom bars, icons (with tooltips) on the side columns."""
        color = core.theme_palette(load_config()["theme"])["text"]
        pairs = [(b, TAB_ICONS.get(name, "blocks"), name, name) for b, (name, _s) in zip(self.tab_buttons, self.TABS)]
        pairs += [(getattr(self, a), icon, text, tip) for a, icon, text, tip in self.FOOT_BUTTONS]
        for b, icon, text, tip in pairs:
            pm = icon_pixmap(icon, 26, color) if side else None
            if side and pm is not None:
                b.setText("")
                b.setIcon(QIcon(pm))
                b.setIconSize(QSize(26, 26))
            else:
                b.setText(text)
                b.setIcon(QIcon())
            b.setToolTip(tip if side else "")
        if not getattr(self, "footer_on", False):     # in the header it's always a small icon
            pm = icon_pixmap("bug", 22, color)
            if pm is not None:
                self.btn_report.setText("")
                self.btn_report.setIcon(QIcon(pm))
                self.btn_report.setIconSize(QSize(22, 22))
            self.btn_report.setToolTip("Report a problem")

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        for w in self.findChildren(QWidget, "dimmer"):
            w.setGeometry(self.rect())

    # ---- theme ----
    def apply_theme(self):
        t = load_config()["theme"]
        pal = core.theme_palette(t)
        scale = int(core.theme_size(t, "scale", GAMEMODE) or 100)
        self.app.setStyleSheet(build_qss(pal, int(scale)))
        if getattr(self, "bars", "top") == "sides":
            self._label_buttons(True)               # re-tint the side icons for the new theme
        mode = t.get("controller_nav", "auto")
        on = mode == "on" or (mode == "auto" and GAMEMODE)
        self.gamepad.set_enabled(on)
        for w in [self.pad_hint, self.hint_lb, self.hint_rb] + [g.lt_rt for g in self.groups]:
            w.setVisible(on)
        if self.health.isVisible():
            self.health.refresh_chart()

    def update_top_status(self):
        sep = "\n" if getattr(self, "bars", "top") == "sides" else "   "
        self.top_status.setText(f"{core.battery_percent().split(' ')[0]}{sep}{time.strftime('%-I:%M %p')}")

    # ---- navigation ----
    def tab_index(self) -> int:
        return getattr(self, "_tab", 0)

    def set_tab(self, i: int, section: int = None):
        i %= len(self.TABS)
        self._tab = i
        for n, b in enumerate(self.tab_buttons):
            b.setChecked(n == i)
        self.stack.setCurrentIndex(i)
        g = self.groups[i]
        g.select(g.index if section is None else section)

    def current_page(self):
        return self.groups[self.tab_index()].current()

    def go(self, name: str):
        if name in self.BROWSE_FILTERS:
            self.browse.set_filter(self.BROWSE_FILTERS[name])
        if name == "Setup":
            self.set_section_hidden("Setup", False)
        name = self.ALIASES.get(name, name)
        for ti, (_tab, secs) in enumerate(self.TABS):
            for si, (n, _attr) in enumerate(secs):
                if n == name:
                    self.set_tab(ti, si)
                    return
        raise KeyError(name)

    def step_page(self, delta: int):
        self.set_tab(self.tab_index() + delta)
        self.tab_buttons[self.tab_index()].setFocus(Qt.OtherFocusReason)

    def step_sub(self, delta: int):
        g = self.groups[self.tab_index()]
        if len(g.visible_indexes()) > 1:
            g.step(delta)
            self.focus_page()

    def focus_tabs(self):
        self.tab_buttons[self.tab_index()].setFocus(Qt.OtherFocusReason)

    def focus_page(self):
        """Focus the top-left control of the page. By position, not creation order: blocks added from other
        objects were created earlier than the page, so creation order would skip past them."""
        page = self.current_page()
        cands = [w for w in page.findChildren(QWidget)
                 if w.isVisible() and w.isEnabled() and (w.focusPolicy() & Qt.TabFocus)
                 and not isinstance(w, QScrollArea)]
        if not cands:
            return

        def where(w):
            p = w.mapTo(page, QPoint(0, 0))
            return (p.y(), p.x())
        w = min(cands, key=where)
        w.setFocus(Qt.OtherFocusReason)
        p = w.parentWidget()
        while p is not None and not isinstance(p, QScrollArea):
            p = p.parentWidget()
        if p is not None:
            p.ensureWidgetVisible(w)

    def gamepad_x(self):
        if self.current_page() is self.browse and self.browse.filter == "plugins":
            self.store_page.search.setFocus()
            QDesktopServices.openUrl(QUrl("steam://open/keyboard"))
        else:
            self.go("Plugin store")

    def on_page_shown(self, page, breadcrumb: bool = True):
        """Every section is fresh when it opens (1.4.0: Games, Saves, Sleep, Storage and Setup used to open
        blank). Blocks from other objects get their owner's refresh too."""
        if breadcrumb:
            core.app_log("gui", f"page: {type(page).__name__}")
        try:
            if page is self.lighting_section:          # per-game previews only animate while they can be seen
                self.automation._anim.start(80)
            else:
                self.automation._anim.stop()
        except AttributeError:
            pass
        if page is not self.setup:
            self.update_setup_chip()
        owners = {self.health: [self.tweaks.refresh], self.sleep: [self.system.refresh],
                  self.storage: [self.system.refresh], self.saves: [self.automation.refresh],
                  self.lighting_section: [self.automation.refresh], self.appearance: [self.system.refresh],
                  self.updates: [self.automation.refresh], self.connect_page: [self.system.refresh]}
        try:
            if page is self.health:
                self.health.refresh()
                self.health.refresh_notices(self.state)
                if not self.doctor.ran and getattr(self, "_refreshed", False):
                    self.doctor.run_checks()          # the first run waits for the first state refresh
            elif hasattr(page, "refresh"):
                page.refresh()
            for f in owners.get(page, []):
                f()
        except Exception:
            core.report_exception("gui-page")

    # ---- state ----
    def refresh(self):
        self.state = core.gather_state()
        self.refresh_password()
        if CATALOG_BY_ID["decky"].check(self.state):
            update_config(lambda c: c["guardian"].__setitem__("decky_expected", True))
        self.health.refresh_notices(self.state)
        self.lighting.refresh()
        self._refreshed = True
        cur = self.current_page()
        if cur is self.health:
            self.doctor.run_checks()          # first time, or fresh after a fix
        # Setup and Games redraw their whole view (ticks and focus would be lost); Home and Browse refresh on show
        if cur not in (self.health, self.browse, self.setup, self.games):
            self.on_page_shown(cur, breadcrumb=False)
        self.update_top_status()
        self.update_cards()

    def update_cards(self):
        pending = self.runner.pending_keys()
        for page in (self.browse,):
            for iid, card in page.cards.items():
                item = CATALOG_BY_ID[iid]
                missing = [CATALOG_BY_ID[r].name for r in item.requires
                           if not CATALOG_BY_ID[r].check(self.state)]
                inst = item.check(self.state)
                off = inst and bool(item.decky_names) and bool(
                    set(core.decky_item_names(item, self.state)) & set(self.state.get("decky_off") or []))
                card.update_state(inst, missing, iid in pending, core.decky_version(item, self.state), off=off)
        self.store_page.refresh_state()

    def toast(self, text: str, ms: int = 3500):
        self.status.setText(text)
        self._toast_timer.start(ms)
        if getattr(self, "bars", "top") == "sides":     # the status text is hidden there: pop the message up
            pop = getattr(self, "_toast_pop", None)
            if pop is None:
                pop = self._toast_pop = QLabel(self)
                pop.setObjectName("toastPop")
                pop.setAttribute(Qt.WA_TransparentForMouseEvents, True)
                self._toast_pop_timer = QTimer(self)
                self._toast_pop_timer.setSingleShot(True)
                self._toast_pop_timer.timeout.connect(pop.hide)
            pop.setText(text)
            pop.adjustSize()
            pop.move(max(0, (self.width() - pop.width()) // 2), max(0, self.height() - pop.height() - 32))
            pop.show()
            pop.raise_()
            self._toast_pop_timer.start(ms)

    def dismiss_alert(self, alert_id):
        alerts = core.read_json(core.DATA_DIR / "alerts.json", []) or []
        core.write_json(core.DATA_DIR / "alerts.json", [a for a in alerts if a.get("id") != alert_id])
        self.health.refresh_notices(self.state)
        if self.doctor.ran:
            self.doctor.run_checks()

    # ---- job events ----
    def on_job_started(self, text: str):
        core.app_log("gui", f"job started: {text}")
        self._toast_timer.stop()
        self.status.setText(f"Working: {text}…")
        self.progress.show()
        self.update_cards()

    def on_job_finished(self, key: str, code: int, tail: str):
        core.app_log("gui", f"job finished: {key} (exit {code})")
        full = core.job_log_tail(key)
        if code == 0 and "Traceback (most recent call last)" in full:      # crashed inside, exited 0 anyway
            core.queue_report("job-error", f"{key}: a script crashed but reported success", full[-20000:],
                              core._fingerprint("job-error", key), attachments=[("Full job output", full)])
        self.state = core.gather_state()
        self.refresh_password()            # always fresh: a stale "no password" reopened passwd in a loop
        item = CATALOG_BY_ID.get(key)
        name = item.name if item else ("Decky plugins" if key == "decky-safe" else key.split(":", 1)[-1])
        failed_msg = None
        if code != 0 and key != "nonsteamlaunchers":     # the Launchers page checks and reports that one
            failed_msg = f"“{name}” failed (exit code {code})."
        elif item and item.kind == "install" and key in self.installing and not item.check(self.state):
            failed_msg = f"The {name} installer finished, but {name} isn't installed."
        if failed_msg:
            core.app_log("gui", f"job {key} failed: code {code}")
            reported = None
            if not IGNORABLE_FAILURES.search(tail or ""):
                reported = core.queue_report("install-failure", f"{name}: {failed_msg}", tail or "(no output)",
                                             core._fingerprint("job", key, code),
                                             attachments=[("Full job output", full)])
            msg_warn(self, APP_NAME, f"{failed_msg}\n\n{tail[-600:]}"
                                + ("\n\nThis was reported automatically." if reported else ""))
        elif not item and core.REFUSAL_PATTERNS.search(tail or ""):
            msg_warn(self, APP_NAME, f"“{name}” may not have worked:\n\n{tail[-600:]}")
        self.installing.discard(key)
        after = self._decky_after.pop(key, None)
        if after:
            after(code == 0)
        if key == "rgb-perms":
            self.lighting.access_job_done(code == 0)
        if key in ("boost-perms", "tuneup", "tuneup-undo"):
            self.performance.job_done(key, code == 0)
        if key == "nonsteamlaunchers":
            self.launchers.job_done(code == 0)
        elif key == "nsl-uninstall":
            self.launchers.uninstall_done(code == 0)
        elif key == "nsl-clean":
            self.launchers.refresh()
        elif key == "storage-clean":
            self.storage.job_done(code == 0)
        elif key == "sleep-nowake":
            self.sleep.job_done(code == 0)
        elif key == "tm-restore":
            self.saves.job_done(code == 0)
        elif key in ("qam-install", "qam-remove"):
            self.games.qam_done(code == 0, key)
        elif key == "game-reset" and code == 0:
            self.toast("Reset done. Start the game to make fresh Windows files.")
        if key == "decky" and self.qam_after_decky:
            self.qam_after_decky = False
            if code == 0 and CATALOG_BY_ID["decky"].check(self.state):
                QTimer.singleShot(1500, self.games.qam_install)
        if key == "decky" and CATALOG_BY_ID["decky"].check(self.state):
            alerts = core.read_json(core.DATA_DIR / "alerts.json", []) or []
            core.write_json(core.DATA_DIR / "alerts.json",
                            [a for a in alerts if not a.get("id", "").startswith("decky-missing")])
        self.refresh()

    def on_idle(self):
        self.progress.hide()
        self.toast("All tasks finished")
        self.update_cards()
        if self.doctor.ran and self.current_page() is self.health:
            self.doctor.run_checks()          # a fix just finished: the Checkup shouldn't show it as a problem

    # ---- actions ----
    # ---- sudo password ----
    def refresh_password(self):
        """Look again (passwd -S is instant). "I already have one" wins over a "no" from passwd, so nobody is
        sent to passwd over and over (the owner, 1.3.2: setup kept asking after the password was set)."""
        found = core.sudo_password_set()
        if found is False and (load_config().get("setup") or {}).get("password_known"):
            found = None
        self.state["password"] = found
        return found

    def assume_password(self):
        update_config(lambda c: c.setdefault("setup", {}).__setitem__("password_known", True))
        self.state["password"] = None
        core.app_log("gui", "password: the owner says one is set")

    def password_window_open(self) -> bool:
        return bool(self._pw_term) and os.path.exists(f"/proc/{self._pw_term}")

    def _watch_password_window(self):
        if not self.password_window_open():
            self.password_window_closed()

    def password_window_closed(self, *_args):
        self._pw_term = None
        self._pw_timer.stop()
        found = self.refresh_password()
        core.app_log("gui", f"password window closed: {found}")
        self.health.refresh_notices(self.state)
        if self.current_page() is self.setup:
            self.setup.refresh()
        if found:
            self.toast("Password is set ✔")

    def needs_password(self) -> bool:
        """True (and helps) only when there's really no sudo password. Checked live every time, since it may
        have been set in the terminal since the last look."""
        if self.state.get("password") is False:
            self.refresh_password()
        if self.state.get("password") is not False:
            return False
        if self.password_window_open():
            self.toast("Finish in the password window first, then try again")
            return True
        choice, ok = ask_item(self, APP_NAME, "This needs a sudo password, and Ally Hub can't find one yet.",
                              ["Create a password", "I already have one"])
        if ok and choice == "I already have one":
            self.assume_password()
            return False
        if ok:
            self.set_password()
        return True

    def on_item_action(self, iid: str, action: str):
        item = CATALOG_BY_ID[iid]
        if iid == "nonsteamlaunchers":          # our own themed picker instead of the script's windows
            self.go("Launchers")
            return
        if action == "open":
            self.launch(item.open_cmd)
            return
        if (iid in ("decky", "tailscale") or item.decky_names) and self.needs_password():
            return
        if action in ("disable", "enable"):
            names = core.decky_item_names(item, self.state)
            if not names:
                self.toast(f"{item.name} not found")
                return
            self.toggle_decky(names, action == "disable", iid)
            return
        if action == "uninstall":
            if not ask(self, f"Remove {item.name}?"):
                return
            cmd = item.uninstall
            if item.decky_names:
                dirs = core.decky_match(item.decky_names, self.state)
                if not dirs:
                    self.toast(f"{item.name} not found")
                    return
                cmd = core.decky_remove_cmd(dirs)
            self.runner.submit(f"Removing {item.name}", cmd, iid)
        else:
            if item.warn and (item.kind == "run" or not item.check(self.state)):
                if not ask(self, f"{item.warn}\n\nContinue with {item.name}?"):
                    return
            self.installing.add(iid)
            verb = "Running" if item.kind == "run" else "Installing"
            self.runner.submit(f"{verb} {item.name}", item.install, iid)
        self.update_cards()

    def on_store_action(self, plugin: dict, action: str):
        name = plugin.get("name", "plugin")
        key = "store:" + name
        if self.needs_password():
            return
        if action in ("disable", "enable"):
            info = self.store_page.installed_for(plugin)
            if info:
                self.toggle_decky([info["name"]], action == "disable", key)
            return
        if action == "uninstall":
            info = self.store_page.installed_for(plugin)
            if not info or not ask(self, f"Remove {name}?"):
                return
            self.runner.submit(f"Removing {name}", core.decky_remove_cmd([info["dir"]]), key)
        else:
            url = core.store_artifact_url(plugin)
            if not url:
                msg_warn(self, APP_NAME, f"{name} has no downloadable release.")
                return
            self.runner.submit(f"Installing plugin {name}", core.decky_store_install_cmd(url, core.store_artifact_hash(plugin)), key)
        self.update_cards()

    def toggle_decky(self, names: list, off: bool, key: str, confirm: bool = True, after=None):
        """Turn Decky plugins off (they stay installed) or back on. Decky restarts for a moment."""
        if self.needs_password():
            return
        if confirm and off and not ask(self, f"Turn off {', '.join(names)}?\n\nIt stays installed and you can turn "
                                             "it back on here. Decky restarts for a moment."):
            return
        cmd = core.decky_toggle_cmd(names, off)
        if not cmd:
            return
        if after:
            self._decky_after[key] = after
        self.runner.submit(f"Turning {'off' if off else 'on'} {', '.join(names)}", cmd, key)
        self.update_cards()

    def remove_decky(self, info: dict):
        if self.needs_password() or not ask(self, f"Remove {info['name']}?"):
            return
        self.runner.submit(f"Removing {info['name']}", core.decky_remove_cmd([info["dir"]]), "decky-mine:" + info["name"])
        self.update_cards()

    def install_essentials(self):
        todo = [i for i in CATALOG if i.recommended and not i.check(self.state)]
        if not todo:
            self.toast("Essentials already installed ✔")
            return
        if self.needs_password():
            return
        names = "\n• ".join(i.name for i in todo)
        if not ask(self, f"Install these?\n\n• {names}"):
            return
        todo.sort(key=lambda i: 0 if i.id == "decky" else 1)
        for i in todo:
            self.installing.add(i.id)
            self.runner.submit(f"Installing {i.name}", i.install, i.id)
        self.update_cards()

    def import_profile(self, prof: dict):
        plan = core.profile_plan(prof, self.state)
        lines = [f"From: {prof.get('device', '?')} ({prof.get('created', '?')})", ""]
        if plan["catalog"]:
            lines.append("Mods: " + ", ".join(CATALOG_BY_ID[i].name for i in plan["catalog"]))
        if plan["flatpaks"]:
            lines.append(f"Apps: {len(plan['flatpaks'])} to install")
        if plan["decky_plugins"]:
            lines.append("Decky plugins: " + ", ".join(plan["decky_plugins"]))
        lines.append("Settings: theme, lighting, automation, game colors, Wake-on-LAN")
        sysp = plan["system"]
        if sysp.get("charge_limit") and sysp["charge_limit"] != "100":
            lines.append(f"Charge limit: {sysp['charge_limit']}%")
        if sysp.get("ssh"):
            lines.append("SSH: on")
        if not ask(self, "Import this profile?\n\n" + "\n".join(lines)):
            return
        needs_root = plan["catalog"] or plan["decky_plugins"] or sysp.get("ssh") or sysp.get("charge_limit")
        if needs_root and self.needs_password():
            return
        core.apply_profile_config(plan["config"])
        self.apply_theme()
        for iid in sorted(plan["catalog"], key=lambda i: 0 if i == "decky" else 1):
            self.installing.add(iid)
            self.runner.submit(f"Installing {CATALOG_BY_ID[iid].name}", CATALOG_BY_ID[iid].install, iid)
        if plan["flatpaks"]:
            cmds = ["flatpak remote-add --user --if-not-exists flathub "
                    "https://dl.flathub.org/repo/flathub.flatpakrepo"]
            cmds += [f"flatpak install --user -y --noninteractive flathub {shlex.quote(f)} "
                     f"|| echo {shlex.quote('Skipped ' + f)}" for f in plan["flatpaks"]]
            self.runner.submit(f"Installing {len(plan['flatpaks'])} apps", "; ".join(cmds), "profile-apps")
        if plan["decky_plugins"]:
            wanted = {p.lower() for p in plan["decky_plugins"]}

            def queue_plugins(plugins):
                for p in plugins:
                    if (p.get("name") or "").lower() in wanted:
                        url = core.store_artifact_url(p)
                        if url:
                            self.runner.submit(f"Installing plugin {p['name']}",
                                               core.decky_store_install_cmd(url, core.store_artifact_hash(p)), "store:" + p["name"])
                self.update_cards()
            self.store_page.with_plugins(queue_plugins)
        if sysp.get("charge_limit") and sysp["charge_limit"] != "100":
            cmd = self.system.charge_limit_cmd(sysp["charge_limit"])
            if cmd:
                self.runner.submit("Restore charge limit", cmd, "charge-limit")
        if sysp.get("ssh") and not core.sshd_active():
            self.runner.submit("Turn SSH on", "sudo systemctl enable --now sshd", "ssh")
        if load_config()["agent"].get("enabled"):
            self.enable_agent()
        self.update_cards()
        self.toast("Importing your profile…")

    def launch(self, cmd: str):
        QProcess.startDetached("bash", ["-c", cmd])
        self.toast("Launching…")

    def set_password(self):
        term = shutil.which("konsole")
        if not term:
            msg_info(self, APP_NAME, "Open a terminal and run:  passwd")
            return
        if self.password_window_open():
            self.toast("The password window is already open")
            return
        script = ('if [ "$(passwd -S 2>/dev/null | cut -d" " -f2)" = P ]; then '
                  'echo "You already have a sudo password. Close this window to keep it,"; '
                  'echo "or type it below to change it."; echo; fi; '
                  "passwd; echo; read -p 'Press Enter to close this window…' _")
        # Detached (closing Ally Hub must not kill it mid-passwd); --separate keeps Konsole from handing the
        # window to a running instance and exiting at once. Ally Hub looks again once that pid is gone.
        res = QProcess.startDetached(term, ["--separate", "-e", "bash", "-c", script])
        ok, pid = res if isinstance(res, tuple) else (bool(res), 0)
        if not ok:
            msg_info(self, APP_NAME, "Couldn't open a terminal. Open Konsole and run:  passwd")
            return
        self._pw_term = int(pid or 0) or None
        if self._pw_term:
            self._pw_timer.start()
        self.toast("Set your password in the terminal window")

    def return_to_game_mode(self):
        if self.runner.busy():
            msg_info(self, APP_NAME, "Wait for the current task to finish first.")
            return
        if GAMEMODE:
            self.close()
        elif shutil.which("steamos-session-select"):
            QProcess.startDetached("steamos-session-select", ["gamescope"])
        else:
            msg_info(self, APP_NAME, "steamos-session-select was not found.")

    def add_to_steam(self):
        res = core.add_to_steam()
        if res == "already":
            self.toast("Ally Hub is already in your Game Mode library")
        elif res == "added":
            self.toast("Added to Steam (restart Steam if it doesn't show up)")
            for delay in (12000, 45000):            # second try in case Steam was slow to add it
                QTimer.singleShot(delay, lambda: self.launchers.fix_artwork(only=["Ally Hub"], quiet=True))
        elif not core.LAUNCHER.exists():
            msg_info(self, APP_NAME, "Run install.sh first so Ally Hub has a launcher.")
        else:
            msg_info(self, APP_NAME, "In Steam: Games > Add a Non-Steam Game, pick Ally Hub, then set its launch "
                                     "options to --gamemode.")

    def enable_led_permissions(self, leds=None) -> bool:
        """Submit the one-time lighting permission job. Returns False if it couldn't start."""
        if self.needs_password():
            return False
        if "rgb-perms" in self.runner.pending_keys():
            self.toast("Already setting up lighting permission…")
            return True
        leds = leds if isinstance(leds, list) else core.find_leds()
        self.runner.submit("Allow lighting without a password", core.led_permission_cmd(leds), "rgb-perms")
        return True

    def use_allyhub_lighting(self, *_args):
        if self.huesync_page.installed() and not ask(
                self, "HueSync is installed too, and the two would fight over the rings.\n\n"
                      "After switching, turn HueSync off: in Game Mode press ••• (Quick Access), open the "
                      "plug icon, tap the gear and disable or uninstall HueSync.\n\nSwitch to Ally Hub?"):
            return
        update_config(lambda c: c["lighting"].__setitem__("controller", "allyhub"))
        self.lighting_section.show_current()
        self.lighting.refresh()
        if core.find_leds() and ask(self, "Ally Hub now controls the rings.\n\nRun the light test to find "
                                          "what your rings need? It takes about a minute."):
            self.lighting.test_lights(auto=True)

    def use_huesync_lighting(self, *_args):
        if not ask(self, "Hand the rings back to HueSync? Ally Hub will stop changing them."):
            return
        update_config(lambda c: c["lighting"].__setitem__("controller", "huesync"))
        self.lighting_section.show_current()
        self.huesync_page.refresh()

    def enable_agent(self):
        update_config(lambda c: c["agent"].__setitem__("enabled", True))
        core.AGENT_UNIT.parent.mkdir(parents=True, exist_ok=True)
        core.AGENT_UNIT.write_text(core.agent_unit_text(sys.executable))
        cmd = ("systemctl --user daemon-reload && systemctl --user enable allyhub-agent.service && "
               "systemctl --user restart allyhub-agent.service && echo 'Background helper running.'")
        self.runner.submit("Start the background helper", cmd, "agent")
        leds = core.find_leds()
        if leds and not core.lighting_shelved() and not core.lighting_access_ok(leds):
            if ask(self, "The background helper changes lighting without asking for a password, which needs a "
                         "one-time permission. Set that up now?"):
                self.enable_led_permissions()

    def disable_agent(self):
        update_config(lambda c: c["agent"].__setitem__("enabled", False))
        self.runner.submit("Stop the background helper",
                           "systemctl --user disable --now allyhub-agent.service; echo 'Background helper stopped.'",
                           "agent")

    def restart_app(self):
        if self.runner.busy() and not ask(self, "A task is still running. Restart anyway?"):
            return
        if _SCALE_SET_BY_US:
            os.environ.pop("QT_SCALE_FACTOR", None)   # let the new process pick the new size
        srv = getattr(self.app, "_instance_server", None)
        if srv is not None:
            srv.close()                                # let the new copy take over as the only instance
        QProcess.startDetached(sys.executable, [str(core.APP_DIR / "allyhub.py")] + sys.argv[1:])
        self.app.quit()

    def show_whats_new(self):
        cfg = load_config()
        last = cfg["updates"].get("last_seen_version")
        if last != VERSION:
            update_config(lambda c: c["updates"].__setitem__("last_seen_version", VERSION))
            notes = core.changelog_section(VERSION)
            if last and notes:
                dlg = QDialog(self)                    # a scrolling panel: release notes can be long
                dlg.setWindowTitle(f"What's new in {core.display_version()}")
                dv = QVBoxLayout(dlg)
                dv.setContentsMargins(24, 20, 24, 20)
                dv.addWidget(label(f"What's new in {core.display_version()}", "cardTitle"))
                body = label("", "cardDesc", wrap=True)
                body.setTextFormat(Qt.MarkdownText)
                body.setText(notes)
                inner = QWidget()
                il = QVBoxLayout(inner)
                il.addWidget(body)
                il.addStretch()
                sa = scroll_page(inner)
                sa.setMinimumHeight(min(420, int(self.height() * 0.55)))
                dv.addWidget(sa, 1)
                row = QHBoxLayout()
                row.addStretch()
                ok = button("OK", dlg.accept, "primary")
                ok.setDefault(True)
                row.addWidget(ok)
                dv.addLayout(row)
                run_dialog(dlg)
        st = core.update_state()
        rb = st.get("rolled_back")
        if rb and not rb.get("ack"):
            self.go("Updates")

    def report_problem(self):
        """One button for anything that's wrong: the user's words plus logs, job output and a system snapshot."""
        if not core.github_token():
            msg_info(self, APP_NAME, "Reports need the GitHub access key. Add it on "
                                                    "Settings → General, then try again.")
            self.go("Updates")
            return
        page = type(self.current_page()).__name__.replace("Page", "")
        text, ok = ask_text(self, "Report a problem",
                            "What went wrong? One line is enough. Ally Hub attaches the logs, "
                            "the last tasks' output and a system snapshot.")
        if not ok:
            return
        path = core.user_report(text, page)
        self.toast("Report sent with everything attached." if path and core.LAST_QUEUE == "queued"
                   else core.report_hint() or "Couldn't save the report.", 7000)

    def send_reports_now(self):
        """Upload queued reports right away instead of waiting for the agent's next pass."""
        def done(r):
            if isinstance(r, tuple) and r[0]:
                self.toast("Report sent. It'll be looked at in the next daily fix-up.", 6000)
            elif isinstance(r, tuple) and r[1]:
                self.toast("Couldn't send the report. Check your access key on Settings → General.", 8000)
        BackgroundTask(self, core.upload_reports, done)

    def maybe_check_updates(self):
        up = load_config()["updates"]
        st = core.update_state()
        if (up.get("auto_update") and not core.agent_running() and not core.on_probation("gui")
                and time.time() - st.get("last_check", 0) > core.UPDATE_INTERVAL_S):
            BackgroundTask(self, core.check_for_update,
                           lambda r: r.get("available") and self.toast(
                               f"Update {core.display_version(r['remote'])} available: see the Updates page", 8000))
        if up.get("reporting") and core.pending_reports() and not core.agent_running():
            BackgroundTask(self, core.upload_reports, lambda r: None)

    def closeEvent(self, ev):
        if self.runner.busy() and not ask(self, "A task is still running. Quit anyway?"):
            ev.ignore()
            return
        core.mark_healthy("gui")          # opened and closed normally: not a failed start, however quick
        ev.accept()


_STARTED = time.time()
_SCALE_SET_BY_US = False


def _excepthook(etype, evalue, tb):
    sys.__excepthook__(etype, evalue, tb)
    reported = core.report_exception("gui", (etype, evalue, tb))
    hint = core.report_hint()
    if core.on_probation("gui") and time.time() - _STARTED < 120:
        ok, _msg = core.rollback(f"Ally Hub's window crashed right after updating: {etype.__name__}: {evalue}")
        if ok:
            core.restart_agent_service()
            msg_error(None, APP_NAME, "The new version of Ally Hub hit an error, so it went "
                                                 "back to the previous version. Restarting…")
            os.execv(sys.executable, [sys.executable, str(core.APP_DIR / "allyhub.py")] + sys.argv[1:])
    msg_warn(None, APP_NAME, f"Something went wrong: {etype.__name__}: {evalue}"
                        + ("\n\nThis was reported automatically." if reported else f"\n\n{hint}"))


INSTANCE_NAME = f"allyhub-{os.getuid()}"


def single_instance(app) -> bool:
    """True if this is the only Ally Hub. Otherwise asks the running one to come to the front."""
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    sock = QLocalSocket()
    sock.connectToServer(INSTANCE_NAME)
    if sock.waitForConnected(500):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        return False
    QLocalServer.removeServer(INSTANCE_NAME)       # a stale socket from a crash
    server = QLocalServer(app)
    server.listen(INSTANCE_NAME)
    app._instance_server = server

    def wake():
        conn = server.nextPendingConnection()
        if conn is not None:
            conn.deleteLater()
        if _HUB is not None:
            if GAMEMODE or "--fullscreen" in sys.argv:
                _HUB.showFullScreen()
            else:
                _HUB.showNormal()
            _HUB.raise_()
            _HUB.activateWindow()
    server.newConnection.connect(wake)
    return True


def main():
    sys.excepthook = _excepthook
    core.app_log("gui", f"start {VERSION} ({'game mode' if GAMEMODE else 'desktop'})")
    try:
        core.sync_testing_rescue()
    except Exception:
        pass
    for fix in (core.migrate_chip_spiral, core.secure_data_dir):
        try:
            fix()
        except Exception:
            pass
    global _SCALE_SET_BY_US
    if "QT_SCALE_FACTOR" not in os.environ:
        os.environ["QT_SCALE_FACTOR"] = str(core.ui_scale(load_config()["theme"], GAMEMODE))
        _SCALE_SET_BY_US = True
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    try:                                            # for reports: how this mode presents the screen
        scr = app.primaryScreen()
        core.app_log("gui", f"screen {scr.size().width()}x{scr.size().height()} dpr {scr.devicePixelRatio():.2f} "
                            f"dpi {scr.logicalDotsPerInch():.0f} qt_scale {os.environ.get('QT_SCALE_FACTOR')} "
                            f"desktop_scale {core.desktop_scale() if not GAMEMODE else '-'}")
    except Exception:
        pass
    if not single_instance(app):                    # already open: it was brought to the front
        core.app_log("gui", "second launch: showed the open window instead")
        return
    # counted only now: tapping the icon while Ally Hub is open isn't a failed start
    if core.startup_check("gui") == "rolled_back":
        app._instance_server.close()
        os.execv(sys.executable, [sys.executable, str(core.APP_DIR / "allyhub.py")] + sys.argv[1:])
    app.setDesktopFileName("allyhub")
    font = QFont("Noto Sans")
    font.setPointSize(11)
    app.setFont(font)
    win = Hub(app)
    if GAMEMODE or "--fullscreen" in sys.argv:
        win.showFullScreen()
    elif core.auto_ui_scale() > 1.0:
        win.showMaximized()     # handheld screen: use all of it
    else:
        win.show()
    if not (load_config().get("setup") or {}).get("done", True):      # a fresh install: walk through setup
        QTimer.singleShot(400, lambda: win.go("Setup"))
    sys.exit(app.exec())
