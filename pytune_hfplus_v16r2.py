#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pytune HF+ V16r2

Professional Linux audio player with real-time FFT spectrum analyzer.

mpv handles playback. FFmpeg decodes a parallel raw PCM stream for the analyzer,
keeping it time-locked to the playback position. All spectrum bars come from real
FFT data — no fake animation.

Quick start:
    ./install.sh
    ./run_pytune_hfplus_v16r2.sh

Dependencies:
    sudo apt install mpv libmpv2 ffmpeg python3-dev build-essential
    pip install PySide6 python-mpv numpy pyFFTW
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QEventLoop,
    QPoint,
    QRect,
    QSortFilterProxyModel,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QAction,
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPixmap,
    QPen,
    QLinearGradient,
    QBrush,
    QShortcut,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QSizePolicy,
    QSlider,
    QSplitter,
    QStatusBar,
    QTableView,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "Pytune HF+"
APP_VERSION = "V16r2"
ORG_NAME = "Pytune"

AUDIO_EXTENSIONS = {
    ".aac", ".aif", ".aiff", ".alac", ".ape", ".flac", ".m4a", ".mka",
    ".mp2", ".mp3", ".mp4", ".oga", ".ogg", ".opus", ".wav", ".weba", ".wma",
}
STREAM_PREFIXES = ("http://", "https://", "rtmp://", "rtsp://", "icy://")
CONFIG_DIR = Path.home() / ".config" / "pytune-hf-plus"
CONFIG_FILE = CONFIG_DIR / "settings_v14.json"

ANALYZER_BACKENDS = [
    ("auto", "Auto Native: C++ FFT if available"),
    ("numpy", "NumPy rFFT fallback"),
    ("fftw", "FFTW: pyFFTW or native C++"),
    ("kissfft", "Native KissFFT-compatible C++"),
    ("pfft", "Native Parallel (local C++ experimental)"),
]
FFT_SIZES = [1024, 2048, 4096, 8192]
BAR_COUNTS = [32, 64, 96, 128]
RENDER_FPS_VALUES = [20, 45, 60]
DEFAULT_RENDER_FPS = 45

SPECTRUM_VISUAL_MODES = [
    # ── Classic professional ───────────────────────────────────────────────
    ("segmented",    "Segmented LED Rack"),
    ("glassbars",    "Glass Gradient Bars"),
    ("dawspectrum",  "DAW Spectrum Analyzer"),
    ("curvetrace",   "Frequency Response Curve"),
    ("vfdbars",      "VFD Broadcast Meter"),
    ("dotmatrix",    "Dot Matrix"),
    ("roundleds",    "Round LED Matrix"),
    # ── DJ / club ─────────────────────────────────────────────────────────
    ("neonpulse",    "Neon Pulse Glow"),
    ("rgbmatrix",    "RGB Frequency Rush"),
    ("mirrorpulse",  "Mirror Pulse Club"),
    # ── Modern / creative ─────────────────────────────────────────────────
    ("mirrorbars",   "Mirror Disco EQ"),
    ("radialhalo",   "Radial Halo Scope"),
    ("splitstereo",  "Split Stereo Towers"),
    ("laserfan",     "Laser Fan Rack"),
    ("pioneerfluoro","Pioneer Fluoro Spectrum"),
    ("technicsbridge","Technics LED VU Bridge"),
    ("sonyes",       "Sony ES Glass Analyzer"),
    ("kenwoodmatrix","Kenwood Dot Matrix Pro"),
    ("boomboxwall",  "Boombox Blinker Wall"),
    ("opposingbridge","Opposing Bridge Meters"),
    ("nightceiling", "Nightclub Ceiling Sweep"),
    ("waterfall",    "Waterfall Cinema"),
]
DEFAULT_SPECTRUM_VISUAL_MODE = "segmented"
DEFAULT_SPECTRUM_THEME = "djgraphite"

SPECTRUM_THEMES: Dict[str, Dict[str, str]] = {
    "djgraphite": {
        "name": "DJ Graphite Pro",
        "bg": "#1e2025", "panel": "#050607", "panel2": "#2b2d32", "grid": "#252a31",
        "grid_major": "#555c67", "border": "#666d77", "accent": "#ff4048", "text": "#f4f5f8", "muted": "#aeb6c2",
        "bar_lo": "#5cff89", "bar_mid": "#ffd84d", "bar_hi": "#ff3f4a",
        "peak": "#ffffff", "vu_off": "#0d1116", "scan": "#ff3a45", "ruler": "#dce3ec",
    },
    "redrack": {
        "name": "Redline Rack Analyzer",
        "bg": "#19090b", "panel": "#060404", "panel2": "#2a1518", "grid": "#321a1d",
        "grid_major": "#65313a", "border": "#8b3641", "accent": "#ff303a", "text": "#ffffff", "muted": "#ffd6da",
        "bar_lo": "#fff2f2", "bar_mid": "#ff8a34", "bar_hi": "#ff2038",
        "peak": "#ffffff", "vu_off": "#160b0d", "scan": "#ff2737", "ruler": "#ffffff",
    },
    "vfdamber": {
        "name": "VFD Amber Broadcast",
        "bg": "#11100c", "panel": "#070603", "panel2": "#242016", "grid": "#342b18",
        "grid_major": "#68512a", "border": "#94703a", "accent": "#ffb74a", "text": "#fff4db", "muted": "#d7bf91",
        "bar_lo": "#5fff8b", "bar_mid": "#ffd86b", "bar_hi": "#ff7a22",
        "peak": "#fff9dd", "vu_off": "#15100a", "scan": "#ffbe55", "ruler": "#ffe3a3",
    },
    "neonbooth": {
        "name": "DJ Neon Booth",
        "bg": "#090713", "panel": "#04050a", "panel2": "#1d132b", "grid": "#253044",
        "grid_major": "#4d627c", "border": "#5e6d8b", "accent": "#ff37c8", "text": "#f5fbff", "muted": "#a9c9da",
        "bar_lo": "#28ff95", "bar_mid": "#00d4ff", "bar_hi": "#ff36d2",
        "peak": "#ffffff", "vu_off": "#080d14", "scan": "#00e6ff", "ruler": "#e6fbff",
    },
    "laserclub": {
        "name": "Laser Club RGB",
        "bg": "#06090f", "panel": "#030506", "panel2": "#121927", "grid": "#172333",
        "grid_major": "#34506d", "border": "#526b88", "accent": "#57faff", "text": "#f1fbff", "muted": "#aac3d2",
        "bar_lo": "#ff2740", "bar_mid": "#31ff68", "bar_hi": "#2f8dff",
        "peak": "#ffffff", "vu_off": "#081018", "scan": "#83ffff", "ruler": "#e7fbff",
    },
    "whiteprecision": {
        "name": "White LED Precision",
        "bg": "#202329", "panel": "#080a0d", "panel2": "#30343b", "grid": "#3a424d",
        "grid_major": "#707b89", "border": "#858c96", "accent": "#ff3636", "text": "#ffffff", "muted": "#d7dde6",
        "bar_lo": "#ffffff", "bar_mid": "#ffb0b0", "bar_hi": "#ff2424",
        "peak": "#ffffff", "vu_off": "#151a20", "scan": "#ff4444", "ruler": "#f4f7fb",
    },
    "titaniumwhite": {
        "name": "Titanium White Studio",
        "bg": "#1b1e23", "panel": "#07090c", "panel2": "#333943", "grid": "#3a424c",
        "grid_major": "#7c8794", "border": "#9aa3ad", "accent": "#ff4545", "text": "#ffffff", "muted": "#d8dee7",
        "bar_lo": "#eaf7ff", "bar_mid": "#ffb7b7", "bar_hi": "#ff2d37",
        "peak": "#ffffff", "vu_off": "#151a20", "scan": "#ff5c5c", "ruler": "#ffffff",
    },
    "cyberblue": {
        "name": "Cyber Blue LCD",
        "bg": "#060b12", "panel": "#02070d", "panel2": "#0d1b2a", "grid": "#12314a",
        "grid_major": "#23618a", "border": "#2f9bd3", "accent": "#49e8ff", "text": "#f2fcff", "muted": "#9fd6ef",
        "bar_lo": "#55ffdd", "bar_mid": "#49a7ff", "bar_hi": "#d7f4ff",
        "peak": "#ffffff", "vu_off": "#06111b", "scan": "#62f6ff", "ruler": "#dffaff",
    },
    "goldbroadcast": {
        "name": "Gold Broadcast Rack",
        "bg": "#15100a", "panel": "#060403", "panel2": "#2f2417", "grid": "#49351e",
        "grid_major": "#9d753d", "border": "#c8964b", "accent": "#ffc15a", "text": "#fff6e1", "muted": "#e0c59a",
        "bar_lo": "#7cff8c", "bar_mid": "#ffe36f", "bar_hi": "#ff8b22",
        "peak": "#fff8dc", "vu_off": "#17100a", "scan": "#ffc45f", "ruler": "#ffe4a8",
    },
    "purplelaser": {
        "name": "Purple Laser Floor",
        "bg": "#090612", "panel": "#05040b", "panel2": "#1b0f2d", "grid": "#2e2350",
        "grid_major": "#6d57a0", "border": "#8a69d8", "accent": "#ff47d2", "text": "#fbf7ff", "muted": "#cdb9ee",
        "bar_lo": "#28fff3", "bar_mid": "#9a5cff", "bar_hi": "#ff47d2",
        "peak": "#ffffff", "vu_off": "#100a1c", "scan": "#ff7ce7", "ruler": "#f7e8ff",
    },
    "emeraldscope": {
        "name": "Emerald Scope Pro",
        "bg": "#06100c", "panel": "#020705", "panel2": "#10241b", "grid": "#173927",
        "grid_major": "#35794f", "border": "#4fbf7a", "accent": "#79ff9f", "text": "#effff4", "muted": "#a8dabb",
        "bar_lo": "#5dff78", "bar_mid": "#28ffd2", "bar_hi": "#ffffff",
        "peak": "#ffffff", "vu_off": "#07130d", "scan": "#7dffa0", "ruler": "#dcffe7",
    },
    "pioneerfluoro": {
        "name": "Pioneer Fluoro Blue",
        "bg": "#071018", "panel": "#02080c", "panel2": "#102332", "grid": "#17384a",
        "grid_major": "#367397", "border": "#5bb8dc", "accent": "#7cf3ff", "text": "#effcff", "muted": "#a7dbe9",
        "bar_lo": "#72ffb0", "bar_mid": "#6ee8ff", "bar_hi": "#e8fbff",
        "peak": "#ffffff", "vu_off": "#06131b", "scan": "#8ff8ff", "ruler": "#d9fbff",
    },
    "technicssilver": {
        "name": "Technics Silver Red",
        "bg": "#181b20", "panel": "#08090b", "panel2": "#2a2f36", "grid": "#363d46",
        "grid_major": "#6f7885", "border": "#9aa6b5", "accent": "#ff3348", "text": "#ffffff", "muted": "#cbd3dc",
        "bar_lo": "#d8fff4", "bar_mid": "#ffcf5a", "bar_hi": "#ff3548",
        "peak": "#ffffff", "vu_off": "#14191f", "scan": "#ff4a5a", "ruler": "#f4f8ff",
    },
    "sonyesblack": {
        "name": "Sony ES Black Glass",
        "bg": "#0b0d10", "panel": "#030405", "panel2": "#191d24", "grid": "#202832",
        "grid_major": "#465363", "border": "#6b7480", "accent": "#66c8ff", "text": "#f8fbff", "muted": "#b7c1ca",
        "bar_lo": "#9cffd2", "bar_mid": "#7cb8ff", "bar_hi": "#ffffff",
        "peak": "#ffffff", "vu_off": "#0a0d12", "scan": "#8ed8ff", "ruler": "#e9f2ff",
    },
    "kenwoodgreen": {
        "name": "Kenwood Matrix Green",
        "bg": "#06100a", "panel": "#020604", "panel2": "#101d13", "grid": "#19331f",
        "grid_major": "#3c7346", "border": "#63b96b", "accent": "#84ff7b", "text": "#efffed", "muted": "#a8d5a7",
        "bar_lo": "#55ff6d", "bar_mid": "#c9ff55", "bar_hi": "#fff9a6",
        "peak": "#ffffff", "vu_off": "#071106", "scan": "#90ff82", "ruler": "#e7ffdd",
    },
    "boomboxchrome": {
        "name": "Boombox Chrome Party",
        "bg": "#151518", "panel": "#060607", "panel2": "#2c2c32", "grid": "#3a3d48",
        "grid_major": "#747b90", "border": "#a0a8b8", "accent": "#ff4cc7", "text": "#ffffff", "muted": "#d7dce6",
        "bar_lo": "#72ff59", "bar_mid": "#27d7ff", "bar_hi": "#ff4cc7",
        "peak": "#ffffff", "vu_off": "#151821", "scan": "#ff77d8", "ruler": "#f0f4ff",
    },
    "nightclubuv": {
        "name": "Nightclub UV Ceiling",
        "bg": "#070512", "panel": "#03030a", "panel2": "#170c2d", "grid": "#25204a",
        "grid_major": "#5f4aa0", "border": "#9174ff", "accent": "#ff45d4", "text": "#fbf7ff", "muted": "#c7b9f0",
        "bar_lo": "#00f0ff", "bar_mid": "#9d59ff", "bar_hi": "#ff4bd8",
        "peak": "#ffffff", "vu_off": "#0c0820", "scan": "#ff8cec", "ruler": "#f7e8ff",
    },
    # ── Classic professional audio hardware & console themes ──────────────
    "neve1073": {
        "name": "Neve 1073 Console",
        "bg": "#1a1208", "panel": "#090800", "panel2": "#2c1e0c", "grid": "#3e2c14",
        "grid_major": "#7c5b2a", "border": "#b08038", "accent": "#e8a030",
        "text": "#f5e8c4", "muted": "#c4a868",
        "bar_lo": "#8aff72", "bar_mid": "#ffd040", "bar_hi": "#ff6820",
        "peak": "#ffe8a0", "vu_off": "#120e04", "scan": "#ffc040", "ruler": "#e8d8a0",
    },
    "ssl4000": {
        "name": "SSL 4000 Console",
        "bg": "#161c20", "panel": "#07090c", "panel2": "#1e2830", "grid": "#2c3840",
        "grid_major": "#587080", "border": "#7090a0", "accent": "#28d888",
        "text": "#e8ecf0", "muted": "#90aabc",
        "bar_lo": "#28e898", "bar_mid": "#60d8ff", "bar_hi": "#ff3440",
        "peak": "#ffffff", "vu_off": "#0c1214", "scan": "#38f0a8", "ruler": "#c8e0f0",
    },
    "harrisonmpc": {
        "name": "Harrison 32C Console",
        "bg": "#141008", "panel": "#070508", "panel2": "#221a10", "grid": "#352818",
        "grid_major": "#705a2e", "border": "#9a8050", "accent": "#d8b060",
        "text": "#f5ead0", "muted": "#c0a870",
        "bar_lo": "#70ff90", "bar_mid": "#ffe060", "bar_hi": "#ff6030",
        "peak": "#ffe8c8", "vu_off": "#100e06", "scan": "#ffc850", "ruler": "#e8d8b0",
    },
    # ── Modern professional DAW / plugin themes ───────────────────────────
    "protools": {
        "name": "Pro Tools DAW Dark",
        "bg": "#181a1c", "panel": "#0b0c0e", "panel2": "#252729", "grid": "#303438",
        "grid_major": "#505860", "border": "#686e76", "accent": "#4ca8ff",
        "text": "#f0f2f5", "muted": "#8a9098",
        "bar_lo": "#28c8f0", "bar_mid": "#60a0ff", "bar_hi": "#ff4060",
        "peak": "#ffffff", "vu_off": "#12141a", "scan": "#38b8ff", "ruler": "#d0d8e0",
    },
    "fabfilter": {
        "name": "FabFilter Pro-Q",
        "bg": "#0e1014", "panel": "#050608", "panel2": "#1c2028", "grid": "#252c36",
        "grid_major": "#404c5c", "border": "#586878", "accent": "#ff9020",
        "text": "#f8f9fa", "muted": "#7888a0",
        "bar_lo": "#30c8e0", "bar_mid": "#f0a030", "bar_hi": "#ff5530",
        "peak": "#ffffff", "vu_off": "#080c10", "scan": "#ffb040", "ruler": "#c8d4e0",
    },
    "izotoprx": {
        "name": "iZotope RX Spectral",
        "bg": "#070f1c", "panel": "#030810", "panel2": "#101828", "grid": "#182030",
        "grid_major": "#2a3d58", "border": "#365898", "accent": "#28a8ff",
        "text": "#e0f0ff", "muted": "#6090bc",
        "bar_lo": "#18e8b0", "bar_mid": "#3888ff", "bar_hi": "#ff4060",
        "peak": "#a0e0ff", "vu_off": "#040c18", "scan": "#20c0ff", "ruler": "#a8d0f0",
    },
    "ozonemod": {
        "name": "Ozone Modern Limiter",
        "bg": "#0e0b18", "panel": "#060410", "panel2": "#1a1628", "grid": "#252038",
        "grid_major": "#483c70", "border": "#6858a8", "accent": "#d050ff",
        "text": "#f5f0ff", "muted": "#8878c8",
        "bar_lo": "#38f8d0", "bar_mid": "#c060ff", "bar_hi": "#ff4080",
        "peak": "#ffffff", "vu_off": "#080618", "scan": "#d860ff", "ruler": "#d0c0f8",
    },
    "abletonlive": {
        "name": "Ableton Live Session",
        "bg": "#1a1a1a", "panel": "#0a0a0a", "panel2": "#272727", "grid": "#333333",
        "grid_major": "#585858", "border": "#707070", "accent": "#ff8800",
        "text": "#f0f0f0", "muted": "#909090",
        "bar_lo": "#a0ff00", "bar_mid": "#ff8800", "bar_hi": "#ff2020",
        "peak": "#ffffff", "vu_off": "#141414", "scan": "#ff9900", "ruler": "#e0e0e0",
    },
}

# Theme key aliases — old settings files may have these names saved.
SPECTRUM_THEME_ALIASES = {
    "onyxdeck": "djgraphite",
    "onyxpro": "djgraphite",
    "onyxglass": "djgraphite",
    "graphite": "djgraphite",
    "redwhite": "redrack",
    "redglass": "redrack",
    "redstudio": "redrack",
    "amberred": "vfdamber",
    "dotmatrixred": "redrack",
    "console": "whiteprecision",
    "studio": "whiteprecision",
    "whiteled": "whiteprecision",
    "titanium": "titaniumwhite",
    "gold": "goldbroadcast",
    "purple": "purplelaser",
    "emerald": "emeraldscope",
    "scopefill": "sonyesblack",
    "pioneer": "pioneerfluoro",
    "technics": "technicssilver",
    "sony": "sonyesblack",
    "kenwood": "kenwoodgreen",
    "boombox": "boomboxchrome",
    "nightclub": "nightclubuv",
}

# Visual mode aliases — maps removed or renamed modes to their replacements.
SPECTRUM_VISUAL_ALIASES = {
    "trace": "sonyes",
    "neonwave": "radialhalo",
    "diamondleds": "roundleds",
    "waterfall": "dawspectrum",
}




def now_stamp() -> str:
    return time.strftime("%H:%M:%S")


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def format_seconds(seconds: Optional[float]) -> str:
    if seconds is None:
        return "--:--"
    try:
        if math.isnan(float(seconds)):
            return "--:--"
        seconds_i = max(0, int(float(seconds)))
    except (TypeError, ValueError):
        return "--:--"
    h = seconds_i // 3600
    m = (seconds_i % 3600) // 60
    s = seconds_i % 60
    if h:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:d}:{s:02d}"


def is_stream_source(source: str) -> bool:
    return source.strip().lower().startswith(STREAM_PREFIXES)


def is_audio_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS


def normalize_source(source: str) -> str:
    source = source.strip()
    if not source:
        return source
    if is_stream_source(source):
        return source
    return str(Path(source).expanduser().resolve())


def title_from_source(source: str) -> str:
    if is_stream_source(source):
        return source
    try:
        p = Path(source)
        return p.stem or p.name or source
    except Exception:
        return source


@dataclass
class Track:
    uid: str
    source: str
    title: str
    kind: str = "file"
    duration: Optional[float] = None

    @classmethod
    def from_source(cls, source: str) -> "Track":
        source = normalize_source(source)
        return cls(
            uid=str(uuid.uuid4()),
            source=source,
            title=title_from_source(source),
            kind="stream" if is_stream_source(source) else "file",
            duration=None,
        )


class SettingsStore:
    def __init__(self, path: Path = CONFIG_FILE) -> None:
        self.path = path
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        try:
            candidates = [
                self.path,
                CONFIG_DIR / "settings_v13.json",
                CONFIG_DIR / "settings_v12.json",
                CONFIG_DIR / "settings_v11.json",
                CONFIG_DIR / "settings_v10.json",
                CONFIG_DIR / "settings_v9.json",
                CONFIG_DIR / "settings_v8.json",
                CONFIG_DIR / "settings_v7.json",
                CONFIG_DIR / "settings_v6.json",
                CONFIG_DIR / "settings_v5.json",
                CONFIG_DIR / "settings.json",
            ]
            self.data = {}
            for candidate in candidates:
                if candidate.exists():
                    self.data = json.loads(candidate.read_text(encoding="utf-8"))
                    break
            # Migrate saved visual mode if it was removed or renamed.
            visual = str(self.data.get("spectrum_visual_mode", DEFAULT_SPECTRUM_VISUAL_MODE))
            if visual in SPECTRUM_VISUAL_ALIASES:
                self.data["spectrum_visual_mode"] = SPECTRUM_VISUAL_ALIASES[visual]
            if not self.path.exists():
                self.data["spectrum_theme"] = DEFAULT_SPECTRUM_THEME
                self.data["spectrum_visual_mode"] = DEFAULT_SPECTRUM_VISUAL_MODE
                self.data["render_fps"] = DEFAULT_RENDER_FPS
        except Exception:
            self.data = {}

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp.replace(self.path)
        except Exception as exc:
            print(f"[settings] save failed: {exc}", file=sys.stderr)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value


class PlaylistModel(QAbstractTableModel):
    COLUMNS = ["#", "Title", "Duration", "Type", "Source"]

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._tracks: List[Track] = []
        self.current_row = -1

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._tracks)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if row < 0 or row >= len(self._tracks):
            return None
        track = self._tracks[row]

        if role == Qt.DisplayRole:
            if col == 0:
                return str(row + 1)
            if col == 1:
                return track.title
            if col == 2:
                return format_seconds(track.duration)
            if col == 3:
                return track.kind.upper()
            if col == 4:
                return track.source

        if role == Qt.TextAlignmentRole:
            if col in (0, 2, 3):
                return int(Qt.AlignCenter)
            return int(Qt.AlignVCenter | Qt.AlignLeft)

        if role == Qt.FontRole and row == self.current_row:
            font = QFont()
            font.setBold(True)
            return font

        if role == Qt.ForegroundRole:
            if row == self.current_row:
                return QColor("#ffffff")
            if track.kind == "stream":
                return QColor("#f6d26b")

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole) -> Any:  # noqa: N802
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return str(section + 1)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        base = super().flags(index)
        if index.isValid():
            return base | Qt.ItemIsSelectable | Qt.ItemIsEnabled
        return base

    def tracks(self) -> List[Track]:
        return list(self._tracks)

    def track_at(self, row: int) -> Optional[Track]:
        if 0 <= row < len(self._tracks):
            return self._tracks[row]
        return None

    def add_tracks(self, tracks: Iterable[Track]) -> Tuple[int, int]:
        incoming = list(tracks)
        if not incoming:
            return 0, 0
        existing = {t.source for t in self._tracks}
        unique: List[Track] = []
        skipped = 0
        for track in incoming:
            if not track.source or track.source in existing:
                skipped += 1
                continue
            existing.add(track.source)
            unique.append(track)
        if not unique:
            return 0, skipped
        start = len(self._tracks)
        end = start + len(unique) - 1
        self.beginInsertRows(QModelIndex(), start, end)
        self._tracks.extend(unique)
        self.endInsertRows()
        return len(unique), skipped

    def remove_rows(self, rows: Iterable[int]) -> int:
        removed = 0
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self._tracks):
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._tracks[row]
                self.endRemoveRows()
                removed += 1
        if self.current_row >= len(self._tracks):
            self.set_current_row(len(self._tracks) - 1)
        return removed

    def clear(self) -> None:
        if not self._tracks:
            return
        self.beginResetModel()
        self._tracks.clear()
        self.current_row = -1
        self.endResetModel()

    def set_current_row(self, row: int) -> None:
        self.current_row = row if 0 <= row < len(self._tracks) else -1
        if self._tracks:
            self.dataChanged.emit(
                self.index(0, 0),
                self.index(len(self._tracks) - 1, self.columnCount() - 1),
                [Qt.DisplayRole, Qt.FontRole, Qt.ForegroundRole],
            )

    def update_duration_by_source(self, source: str, duration: Optional[float]) -> None:
        for row, track in enumerate(self._tracks):
            if track.source == source:
                track.duration = duration
                self.dataChanged.emit(self.index(row, 2), self.index(row, 2), [Qt.DisplayRole])
                return

    def move_up(self, rows: Iterable[int]) -> None:
        selected = sorted(set(rows))
        if not selected or selected[0] <= 0:
            return
        self.beginResetModel()
        for row in selected:
            self._tracks[row - 1], self._tracks[row] = self._tracks[row], self._tracks[row - 1]
            if self.current_row == row:
                self.current_row = row - 1
            elif self.current_row == row - 1:
                self.current_row = row
        self.endResetModel()

    def move_down(self, rows: Iterable[int]) -> None:
        selected = sorted(set(rows), reverse=True)
        if not selected or selected[0] >= len(self._tracks) - 1:
            return
        self.beginResetModel()
        for row in selected:
            self._tracks[row + 1], self._tracks[row] = self._tracks[row], self._tracks[row + 1]
            if self.current_row == row:
                self.current_row = row + 1
            elif self.current_row == row + 1:
                self.current_row = row
        self.endResetModel()

    def to_jsonable(self) -> List[Dict[str, Any]]:
        return [asdict(t) for t in self._tracks]

    def load_jsonable(self, payload: Any) -> None:
        if not isinstance(payload, list):
            return
        tracks: List[Track] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source", "")).strip()
            if not source:
                continue
            tracks.append(
                Track(
                    uid=str(item.get("uid") or uuid.uuid4()),
                    source=source,
                    title=str(item.get("title") or title_from_source(source)),
                    kind=str(item.get("kind") or ("stream" if is_stream_source(source) else "file")),
                    duration=item.get("duration"),
                )
            )
        self.add_tracks(tracks)


class PlaylistProxyModel(QSortFilterProxyModel):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterKeyColumn(-1)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:  # noqa: N802
        pattern = self.filterRegularExpression().pattern()
        if not pattern:
            return True
        model = self.sourceModel()
        if model is None:
            return True
        needle = pattern.lower()
        for col in (1, 3, 4):
            idx = model.index(source_row, col, source_parent)
            text = str(model.data(idx, Qt.DisplayRole) or "").lower()
            if needle in text:
                return True
        return False


class FileScanWorker(QObject):
    found = Signal(list)
    progress = Signal(str, int)
    error = Signal(str)
    finished = Signal()

    def __init__(self, roots: List[str], recursive: bool = True) -> None:
        super().__init__()
        self.roots = roots
        self.recursive = recursive
        self._stop_requested = threading.Event()

    @Slot()
    def run(self) -> None:
        count = 0
        batch: List[str] = []
        try:
            for root_str in self.roots:
                if self._stop_requested.is_set():
                    break
                root = Path(root_str).expanduser()
                if not root.exists():
                    self.error.emit(f"Scan path does not exist: {root}")
                    continue
                iterator: Iterable[Path]
                if root.is_file():
                    iterator = [root]
                elif self.recursive:
                    iterator = root.rglob("*")
                else:
                    iterator = root.glob("*")

                for path in iterator:
                    if self._stop_requested.is_set():
                        break
                    try:
                        if is_audio_file(path):
                            batch.append(str(path.resolve()))
                            count += 1
                            if len(batch) >= 64:
                                self.found.emit(batch)
                                batch = []
                        if count and count % 100 == 0:
                            self.progress.emit(str(path), count)
                    except Exception as exc:
                        self.error.emit(f"Scan skipped {path}: {exc}")
            if batch:
                self.found.emit(batch)
            self.progress.emit("scan-complete", count)
        except Exception as exc:
            self.error.emit(f"Scan failed: {exc}")
        finally:
            self.finished.emit()

    @Slot()
    def stop(self) -> None:
        self._stop_requested.set()


class MpvEngine(QObject):
    log_line = Signal(str)
    error = Signal(str)
    state_changed = Signal(str)
    position_changed = Signal(float, float)
    metadata_changed = Signal(dict)
    eof_reached = Signal()
    source_changed = Signal(str)
    duration_changed = Signal(str, float)
    audio_outputs_changed = Signal(list)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._lock = threading.RLock()
        self._mpv: Any = None
        self._source = ""
        self._duration = 0.0
        self._position = 0.0
        self._state = "idle"
        self.available = False
        self._init_mpv()

    def _init_mpv(self) -> None:
        try:
            import mpv  # type: ignore

            self._mpv = mpv.MPV(
                ytdl=False,
                video=False,
                vo="null",
                input_default_bindings=False,
                input_vo_keyboard=False,
                osc=False,
                audio_display="no",
                keep_open="no",
                log_handler=self._mpv_log_handler,
                loglevel="warn",
            )
            self.available = True
            self._safe_observe("time-pos", self._on_time_pos)
            self._safe_observe("duration", self._on_duration)
            self._safe_observe("metadata", self._on_metadata)
            self._safe_observe("pause", self._on_pause)
            self._safe_observe("idle-active", self._on_idle)
            self._safe_observe("eof-reached", self._on_eof)
            self._install_event_callback()
            self.log_line.emit("mpv backend initialized")
            QTimer.singleShot(0, self.refresh_audio_outputs)
        except Exception as exc:
            self.available = False
            self._mpv = None
            self.error.emit(
                "mpv backend failed to initialize. Install dependencies: "
                "sudo apt install mpv libmpv2 && pip install python-mpv. "
                f"Error: {exc}"
            )

    def _install_event_callback(self) -> None:
        if self._mpv is None:
            return
        try:
            @self._mpv.event_callback("end-file")
            def _end_file_event(event: Any) -> None:
                del event
                self.log_line.emit("mpv end-file event")
                self.eof_reached.emit()
        except Exception as exc:
            self.log_line.emit(f"mpv end-file callback not installed: {exc}")

    def _safe_observe(self, name: str, callback: Any) -> None:
        try:
            self._mpv.observe_property(name, callback)
        except Exception as exc:
            self.log_line.emit(f"mpv property observe failed for {name}: {exc}")

    def _mpv_log_handler(self, loglevel: str, component: str, message: str) -> None:
        message = message.strip()
        if message:
            self.log_line.emit(f"mpv[{loglevel}:{component}] {message}")

    def _on_time_pos(self, name: str, value: Any) -> None:
        del name
        pos = safe_float(value, 0.0)
        with self._lock:
            self._position = pos
            duration = self._duration
        self.position_changed.emit(pos, duration)

    def _on_duration(self, name: str, value: Any) -> None:
        del name
        duration = safe_float(value, 0.0)
        with self._lock:
            self._duration = duration
            source = self._source
            pos = self._position
        self.duration_changed.emit(source, duration)
        self.position_changed.emit(pos, duration)

    def _on_metadata(self, name: str, value: Any) -> None:
        del name
        self.metadata_changed.emit(dict(value) if isinstance(value, dict) else {})

    def _on_pause(self, name: str, value: Any) -> None:
        del name
        paused = bool(value)
        with self._lock:
            if self._source:
                self._state = "paused" if paused else "playing"
            else:
                self._state = "idle"
            state = self._state
        self.state_changed.emit(state)

    def _on_idle(self, name: str, value: Any) -> None:
        del name
        if bool(value):
            with self._lock:
                self._state = "idle" if not self._source else "stopped"
                state = self._state
            self.state_changed.emit(state)

    def _on_eof(self, name: str, value: Any) -> None:
        del name
        if bool(value):
            self.log_line.emit("mpv EOF reached")
            self.eof_reached.emit()

    def _require_mpv(self) -> bool:
        if not self.available or self._mpv is None:
            self.error.emit("mpv backend is not available")
            return False
        return True

    def load(self, source: str, start_pos: float = 0.0) -> None:
        source = normalize_source(source)
        start_pos = max(0.0, float(start_pos or 0.0))
        if not source or not self._require_mpv():
            return
        try:
            with self._lock:
                self._source = source
                self._duration = 0.0
                self._position = start_pos
                self._state = "loading"
            self.source_changed.emit(source)
            self.state_changed.emit("loading")
            self.log_line.emit(f"loadfile: {source}" + (f" @ {format_seconds(start_pos)}" if start_pos > 0.05 else ""))
            if start_pos > 0.05 and not is_stream_source(source):
                try:
                    self._mpv.command("loadfile", source, "replace", f"start={start_pos:.3f}")
                except Exception:
                    self._mpv.command("loadfile", source, "replace")
                    QTimer.singleShot(250, lambda: self.seek_absolute(start_pos))
            else:
                self._mpv.command("loadfile", source, "replace")
            self._mpv.pause = False
        except Exception as exc:
            self.error.emit(f"mpv load failed: {exc}")

    @Slot()
    def play(self) -> None:
        if not self._require_mpv():
            return
        try:
            self._mpv.pause = False
            self.state_changed.emit("playing")
        except Exception as exc:
            self.error.emit(f"mpv play failed: {exc}")

    @Slot()
    def toggle_pause(self) -> None:
        if not self._require_mpv():
            return
        try:
            current = bool(getattr(self._mpv, "pause", False))
            self._mpv.pause = not current
        except Exception as exc:
            self.error.emit(f"mpv toggle pause failed: {exc}")

    @Slot()
    def stop(self) -> None:
        if not self._require_mpv():
            return
        try:
            self._mpv.command("stop")
            with self._lock:
                self._position = 0.0
                self._duration = 0.0
                self._source = ""
                self._state = "stopped"
            self.position_changed.emit(0.0, 0.0)
            self.state_changed.emit("stopped")
        except Exception as exc:
            self.error.emit(f"mpv stop failed: {exc}")

    @Slot(float)
    def seek_absolute(self, seconds: float) -> None:
        if not self._require_mpv():
            return
        try:
            self._mpv.command("seek", float(max(0.0, seconds)), "absolute", "exact")
        except Exception as exc:
            self.error.emit(f"mpv seek failed: {exc}")

    @Slot(float)
    def seek_relative(self, seconds: float) -> None:
        if not self._require_mpv():
            return
        try:
            self._mpv.command("seek", float(seconds), "relative", "exact")
        except Exception as exc:
            self.error.emit(f"mpv relative seek failed: {exc}")

    @Slot(int)
    def set_volume(self, volume: int) -> None:
        if not self._require_mpv():
            return
        volume = max(0, min(130, int(volume)))
        try:
            self._mpv.volume = volume
        except Exception as exc:
            self.error.emit(f"mpv volume failed: {exc}")

    def _get_property(self, name: str, default: Any = None) -> Any:
        if self._mpv is None:
            return default
        try:
            getter = getattr(self._mpv, "get_property", None)
            if callable(getter):
                return getter(name)
        except Exception:
            pass
        try:
            return getattr(self._mpv, name.replace("-", "_"))
        except Exception:
            return default

    def _set_property(self, name: str, value: Any) -> bool:
        if self._mpv is None:
            return False
        try:
            setter = getattr(self._mpv, "set_property", None)
            if callable(setter):
                setter(name, value)
                return True
        except Exception:
            pass
        try:
            setattr(self._mpv, name.replace("-", "_"), value)
            return True
        except Exception:
            pass
        try:
            self._mpv.command("set", name, value)
            return True
        except Exception:
            return False

    def _run_system_command(self, args: List[str], timeout: float = 1.6) -> str:
        try:
            proc = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)
            return proc.stdout or ""
        except Exception:
            return ""

    def _scan_pactl_sinks(self) -> List[Dict[str, str]]:
        sinks: List[Dict[str, str]] = []
        if shutil.which("pactl") is None:
            return sinks
        text = self._run_system_command(["pactl", "-f", "json", "list", "sinks"], timeout=1.8)
        if text.strip():
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    for item in parsed:
                        if not isinstance(item, dict):
                            continue
                        name = str(item.get("name") or "").strip()
                        if not name or ".monitor" in name.lower() or "monitor" == name.lower():
                            continue
                        props = item.get("properties") if isinstance(item.get("properties"), dict) else {}
                        media_class = str(props.get("media.class") or props.get("device.class") or "").lower()
                        if "monitor" in media_class:
                            continue
                        desc = str(item.get("description") or props.get("device.description") or props.get("node.description") or name).strip()
                        state = str(item.get("state") or "").strip()
                        sinks.append({"sink_name": name, "description": desc, "state": state})
            except Exception as exc:
                self.log_line.emit(f"pactl JSON sink scan failed: {exc}")

        if not sinks:
            text = self._run_system_command(["pactl", "list", "short", "sinks"], timeout=1.4)
            for line in text.splitlines():
                parts = line.split("\t")
                if len(parts) < 2:
                    continue
                name = parts[1].strip()
                if not name or ".monitor" in name.lower():
                    continue
                sinks.append({"sink_name": name, "description": name, "state": ""})

        unique: List[Dict[str, str]] = []
        seen = set()
        for sink in sinks:
            key = sink["sink_name"]
            if key in seen:
                continue
            seen.add(key)
            unique.append(sink)
        return unique

    def _match_mpv_device_for_sink(self, sink_name: str, sink_desc: str, mpv_devices: List[Dict[str, str]]) -> str:
        exact_names = [f"pulse/{sink_name}", f"pipewire/{sink_name}", sink_name]
        by_name = {str(d.get("name") or ""): str(d.get("name") or "") for d in mpv_devices}
        for candidate in exact_names:
            if candidate in by_name:
                return candidate
        sink_l = sink_name.lower()
        desc_l = sink_desc.lower()
        best = ""
        for dev in mpv_devices:
            name = str(dev.get("name") or "")
            desc = str(dev.get("description") or "")
            low_name = name.lower()
            low_desc = desc.lower()
            if not name or low_name == "auto" or "null" in low_name or "monitor" in low_name:
                continue
            if sink_l and sink_l in low_name:
                return name
            if sink_l and sink_l in low_desc:
                best = name
            elif desc_l and desc_l in low_desc:
                best = name
        # On Linux/PipeWire-Pulse, mpv accepts pulse/<sink-name> even when its device-list is noisy.
        return best or f"pulse/{sink_name}"

    def _fallback_filtered_mpv_outputs(self, mpv_devices: List[Dict[str, str]]) -> List[Dict[str, str]]:
        outputs: List[Dict[str, str]] = []
        seen = set()
        skip_tokens = (
            "null", "monitor", "openal", "jack", "oss", "sndio", "rsound", "default", "auto",
            "surround", "front:", "rear:", "center_lfe", "side:", "iec958:", "spdif", "dmix", "dsnoop", "pulse/default",
        )
        keep_prefixes = ("pulse/", "pipewire/", "alsa/hw:", "coreaudio/", "wasapi/", "audiounit/")
        for item in mpv_devices:
            name = str(item.get("name") or "").strip()
            desc = str(item.get("description") or name).strip()
            low = f"{name} {desc}".lower()
            if not name or name in seen:
                continue
            if any(tok in low for tok in skip_tokens):
                continue
            if not name.lower().startswith(keep_prefixes):
                continue
            seen.add(name)
            outputs.append({"name": name, "description": desc, "real": "mpv-filtered"})
        return outputs

    @Slot()
    def refresh_audio_outputs(self) -> None:
        outputs: List[Dict[str, str]] = [{"name": "auto", "description": "System default output", "real": "default"}]
        if not self._require_mpv():
            self.audio_outputs_changed.emit(outputs)
            return
        raw = self._get_property("audio-device-list", [])
        mpv_devices = [x for x in raw if isinstance(x, dict)] if isinstance(raw, list) else []

        real_sinks = self._scan_pactl_sinks()
        seen = {"auto"}
        if real_sinks:
            for sink in real_sinks:
                sink_name = str(sink.get("sink_name") or "").strip()
                if not sink_name:
                    continue
                desc = str(sink.get("description") or sink_name).strip()
                mpv_name = self._match_mpv_device_for_sink(sink_name, desc, mpv_devices)
                if mpv_name in seen:
                    continue
                outputs.append({"name": mpv_name, "description": desc, "sink_name": sink_name, "real": "pactl"})
                seen.add(mpv_name)
            self.log_line.emit(f"system audio scan: {len(real_sinks)} real output sink(s), {len(outputs)-1} shown")
        else:
            fallback = self._fallback_filtered_mpv_outputs(mpv_devices)
            for item in fallback:
                name = str(item.get("name") or "")
                if not name or name in seen:
                    continue
                outputs.append(item)
                seen.add(name)
            self.log_line.emit(f"system audio scan: pactl unavailable/no sinks; {len(outputs)-1} filtered mpv output(s) shown")

        self.audio_outputs_changed.emit(outputs)

    @Slot(str)
    def set_audio_output(self, device_name: str) -> None:
        device_name = (device_name or "auto").strip() or "auto"
        if not self._require_mpv():
            return
        if self._set_property("audio-device", device_name):
            self.log_line.emit(f"audio output selected: {device_name}")
        else:
            self.error.emit(f"failed to select audio output: {device_name}")

    def state_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "source": self._source,
                "duration": self._duration,
                "position": self._position,
                "state": self._state,
            }

    def shutdown(self) -> None:
        if self._mpv is None:
            return
        try:
            self._mpv.terminate()
        except Exception:
            pass


class RealFftAnalyzer(QObject):
    frame_ready = Signal(object)
    log_line = Signal(str)
    error = Signal(str)
    status_changed = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._lock = threading.RLock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event: Optional[threading.Event] = None
        self._proc: Optional[subprocess.Popen[bytes]] = None
        self._source = ""
        self._state = "idle"
        self._mpv_pos = 0.0
        self._decode_pos = 0.0
        self._session = 0
        self._restart_requested = False
        self._restart_pos = 0.0
        self._bars = 64
        self._sample_rate = 44100
        self._frame_samples = 2048
        self._target_fps = DEFAULT_RENDER_FPS
        self._backend = "auto"
        self._active_backend = "not-started"
        self._backend_reason = "not started"
        self._display_peak_db = -72.0
        self._window_cache: Any = None
        self._bin_edges_cache: Any = None

    def set_target_fps(self, fps: int) -> None:
        try:
            fps = int(fps)
        except Exception:
            fps = DEFAULT_RENDER_FPS
        fps = max(15, min(60, fps))
        with self._lock:
            changed = fps != self._target_fps
            self._target_fps = fps
            source = self._source
            pos = self._mpv_pos
            state = self._state
        self.status_changed.emit(f"target-fps={fps}")
        if changed and source and state in ("playing", "loading"):
            self.request_resync(pos)

    def set_backend(self, backend: str) -> None:
        backend = (backend or "auto").strip().lower()
        valid = {key for key, _ in ANALYZER_BACKENDS}
        if backend not in valid:
            backend = "auto"
        with self._lock:
            changed = backend != self._backend
            self._backend = backend
            if changed:
                self._display_peak_db = -72.0
                self._window_cache = None
                self._bin_edges_cache = None
            source = self._source
            pos = self._mpv_pos
            state = self._state
        self.status_changed.emit(f"requested-backend={backend}")
        if changed and source and state in ("playing", "loading"):
            self.request_resync(pos)

    def set_fft_size(self, frame_samples: int) -> None:
        try:
            frame_samples = int(frame_samples)
        except Exception:
            frame_samples = 2048
        if frame_samples not in FFT_SIZES:
            frame_samples = 2048
        with self._lock:
            changed = frame_samples != self._frame_samples
            self._frame_samples = frame_samples
            self._window_cache = None
            self._bin_edges_cache = None
            source = self._source
            pos = self._mpv_pos
            state = self._state
        self.status_changed.emit(f"fft-size={frame_samples}")
        if changed and source and state in ("playing", "loading"):
            self.request_resync(pos)

    def set_bar_count(self, bar_count: int) -> None:
        try:
            bar_count = int(bar_count)
        except Exception:
            bar_count = 64
        if bar_count not in BAR_COUNTS:
            bar_count = 64
        with self._lock:
            changed = bar_count != self._bars
            self._bars = bar_count
            self._window_cache = None
            self._bin_edges_cache = None
            source = self._source
            pos = self._mpv_pos
            state = self._state
        self.status_changed.emit(f"bars={bar_count}")
        if changed and source and state in ("playing", "loading"):
            self.request_resync(pos)

    def start(self, source: str, start_pos: float = 0.0) -> None:
        source = normalize_source(source)
        if not source:
            return
        self.stop(non_blocking=True)
        with self._lock:
            self._session += 1
            session = self._session
            self._source = source
            self._mpv_pos = max(0.0, float(start_pos))
            self._decode_pos = max(0.0, float(start_pos))
            self._state = "playing"
            self._restart_requested = False
            self._restart_pos = max(0.0, float(start_pos))
            stop_event = threading.Event()
            self._stop_event = stop_event
        self.status_changed.emit("analyzer-starting")
        thread = threading.Thread(
            target=self._thread_main,
            args=(session, source, max(0.0, float(start_pos)), stop_event),
            name="PytuneFftAnalyzer",
            daemon=True,
        )
        with self._lock:
            self._thread = thread
        thread.start()

    def stop(self, non_blocking: bool = True) -> None:
        with self._lock:
            stop_event = self._stop_event
            proc = self._proc
            self._state = "stopped"
        if stop_event is not None:
            stop_event.set()
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass
        if not non_blocking:
            thread = self._thread
            if thread is not None and thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=0.25)
        self.status_changed.emit("stopped")

    def set_playback_state(self, state: str) -> None:
        with self._lock:
            self._state = state
        self.status_changed.emit(state)

    def update_mpv_position(self, position: float, state: str) -> None:
        with self._lock:
            self._mpv_pos = max(0.0, float(position))
            self._state = state
            decode_pos = self._decode_pos
            source = self._source
        if source and state == "playing" and not is_stream_source(source):
            if abs(decode_pos - position) > 1.35:
                self.request_resync(position)

    def request_resync(self, position: float) -> None:
        with self._lock:
            self._restart_requested = True
            self._restart_pos = max(0.0, float(position))
            proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

    def _thread_main(self, session: int, source: str, start_pos: float, stop_event: threading.Event) -> None:
        if shutil.which("ffmpeg") is None:
            self.error.emit("FFmpeg is not installed. Install it with: sudo apt install ffmpeg")
            self.status_changed.emit("ffmpeg-missing")
            return
        try:
            import numpy as np  # type: ignore
        except Exception as exc:
            self.error.emit(f"NumPy is required for real FFT analysis: {exc}")
            self.status_changed.emit("numpy-missing")
            return

        with self._lock:
            requested_backend = self._backend
        active_backend, fft_context = self._prepare_fft_backend(requested_backend)
        with self._lock:
            self._active_backend = active_backend
            self._backend_reason = str(fft_context.get("backend_reason", "active"))
            backend_reason = self._backend_reason
        self.status_changed.emit(f"active-backend={active_backend};requested={requested_backend};reason={backend_reason}")

        pos = max(0.0, start_pos)
        while not stop_event.is_set():
            with self._lock:
                self._restart_requested = False
                self._restart_pos = pos
            self._decode_loop(np, session, source, pos, stop_event, active_backend, requested_backend, fft_context)
            with self._lock:
                should_restart = self._restart_requested and not stop_event.is_set() and session == self._session
                pos = self._restart_pos
            if should_restart:
                self.log_line.emit(f"analyzer resync -> {format_seconds(pos)}")
                continue
            break
        self.status_changed.emit("stopped" if stop_event.is_set() else "ended")

    def _prepare_fft_backend(self, requested_backend: str) -> Tuple[str, Dict[str, Any]]:
        requested_backend = (requested_backend or "auto").lower()
        context: Dict[str, Any] = {"backend_reason": "pending"}

        def try_native(native_request: str) -> bool:
            try:
                import pytune_hfplus_native_fft as native_fft  # type: ignore
                if not hasattr(native_fft, "rfft_magnitude"):
                    context["native_error"] = "module loaded but rfft_magnitude() is missing"
                    return False
                name = str(native_fft.backend_name(native_request)) if hasattr(native_fft, "backend_name") else "Native C++ FFT"
                context["native_fft"] = native_fft
                context["backend_reason"] = name
                if hasattr(native_fft, "engine_info"):
                    try:
                        context["native_info"] = native_fft.engine_info()
                    except Exception:
                        pass
                self.log_line.emit(f"FFT backend: {name}")
                return True
            except Exception as exc:
                context["native_error"] = str(exc)
                return False

        def try_pyfftw() -> bool:
            try:
                import pyfftw  # type: ignore
                import pyfftw.interfaces.numpy_fft as pyfftw_fft  # type: ignore
                pyfftw.interfaces.cache.enable()
                context["pyfftw_fft"] = pyfftw_fft
                context["backend_reason"] = "pyFFTW available"
                return True
            except Exception as exc:
                context["fftw_error"] = str(exc)
                return False

        # Auto: prefer the native C++ module, then pyFFTW, then NumPy as last resort.
        if requested_backend == "auto":
            if try_native("kissfft"):
                return "kissfft", context
            if try_pyfftw():
                self.log_line.emit("FFT backend auto-selected: FFTW via pyFFTW")
                context["backend_reason"] = "auto selected pyFFTW"
                return "fftw", context
            self.error.emit("Native FFT module was not importable; using NumPy fallback. Run ./native/build_native.sh --core-only")
            context["backend_reason"] = "native unavailable; NumPy fallback"
            return "numpy", context

        if requested_backend == "fftw":
            if try_pyfftw():
                self.log_line.emit("FFT backend: FFTW via pyFFTW")
                context["backend_reason"] = "pyFFTW available"
                return "fftw", context
            if try_native("fftw"):
                return "fftw", context
            self.error.emit("FFTW requested but pyFFTW/native FFT module is unavailable; NumPy fallback is active")
            context["backend_reason"] = "FFTW unavailable; NumPy fallback"
            return "numpy", context

        if requested_backend in ("kissfft", "pfft"):
            if try_native(requested_backend):
                return requested_backend, context
            self.error.emit(f"{requested_backend.upper()} requested but native FFT module is unavailable; NumPy fallback is active")
            context["backend_reason"] = f"{requested_backend.upper()} native unavailable; NumPy fallback"
            return "numpy", context

        self.log_line.emit("FFT backend: NumPy rFFT")
        context["backend_reason"] = "NumPy rFFT active" if requested_backend in ("numpy",) else "NumPy fallback"
        return "numpy", context

    def _ffmpeg_command(self, source: str, start_pos: float) -> List[str]:
        cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-loglevel", "error"]
        if not is_stream_source(source) and start_pos > 0.05:
            cmd += ["-ss", f"{start_pos:.3f}"]
        cmd += ["-i", source, "-map", "0:a:0", "-vn", "-ac", "2", "-ar", str(self._sample_rate), "-f", "f32le", "pipe:1"]
        return cmd

    def _read_exact(self, pipe: Any, size: int, stop_event: threading.Event) -> bytes:
        chunks: List[bytes] = []
        remaining = size
        while remaining > 0 and not stop_event.is_set():
            chunk = pipe.read(remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _decode_loop(self, np: Any, session: int, source: str, start_pos: float, stop_event: threading.Event, active_backend: str, requested_backend: str, fft_context: Dict[str, Any]) -> None:
        stream_mode = is_stream_source(source)
        cmd = self._ffmpeg_command(source, start_pos)
        with self._lock:
            fft_samples = int(self._frame_samples)
            target_fps = int(self._target_fps)
        hop_samples = max(256, min(fft_samples, int(round(self._sample_rate / max(1, target_fps)))))
        bytes_per_hop = hop_samples * 2 * 4
        frames_emitted = 0
        samples_read = 0
        last_fps_t = time.perf_counter()
        current_fps = 0.0
        t_open = time.perf_counter()
        window_left = np.zeros(fft_samples, dtype=np.float32)
        window_right = np.zeros(fft_samples, dtype=np.float32)

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=bytes_per_hop * 16,
            )
        except Exception as exc:
            self.error.emit(f"FFmpeg analyzer failed to start: {exc}")
            return

        with self._lock:
            if session != self._session:
                try:
                    proc.terminate()
                except Exception:
                    pass
                return
            self._proc = proc
        self.status_changed.emit("decoding-real-pcm")
        self.log_line.emit(f"analyzer ffmpeg started at {format_seconds(start_pos)} | fft={active_backend} | source={source}")

        assert proc.stdout is not None
        try:
            while not stop_event.is_set():
                with self._lock:
                    state = self._state
                    mpv_pos = self._mpv_pos
                    restart_requested = self._restart_requested
                    active_session = self._session
                if active_session != session:
                    break
                if restart_requested:
                    break
                if state not in ("playing", "loading"):
                    time.sleep(0.035)
                    continue

                decode_pos = start_pos + (samples_read / float(self._sample_rate))
                if not stream_mode:
                    # Keep analyzer slightly ahead but not racing away from mpv.
                    ahead = decode_pos - mpv_pos
                    if ahead > 0.22:
                        time.sleep(min(0.055, ahead / 2.0))
                        continue
                    if mpv_pos - decode_pos > 1.35:
                        with self._lock:
                            self._restart_requested = True
                            self._restart_pos = mpv_pos
                        break
                else:
                    expected_wall = t_open + (samples_read / float(self._sample_rate))
                    wall_ahead = expected_wall - time.perf_counter()
                    if wall_ahead > 0:
                        time.sleep(min(0.04, wall_ahead))

                with self._lock:
                    new_target_fps = int(self._target_fps)
                    new_fft_samples = int(self._frame_samples)
                if new_target_fps != target_fps or new_fft_samples != fft_samples:
                    with self._lock:
                        self._restart_requested = True
                        self._restart_pos = mpv_pos
                    break

                raw = self._read_exact(proc.stdout, bytes_per_hop, stop_event)
                if len(raw) < bytes_per_hop:
                    if not stop_event.is_set():
                        rc = proc.poll()
                        self.status_changed.emit("ffmpeg-short-read")
                        self.error.emit(f"FFmpeg analyzer produced a short PCM hop {len(raw)}/{bytes_per_hop}; rc={rc}. Check source codec/path and FFmpeg log.")
                    break

                t_fft0 = time.perf_counter()
                pcm = np.frombuffer(raw, dtype=np.float32)
                if pcm.size < hop_samples * 2:
                    break
                stereo = pcm.reshape(-1, 2)
                hop_left = stereo[:, 0]
                hop_right = stereo[:, 1]
                if hop_samples >= fft_samples:
                    window_left[:] = hop_left[-fft_samples:]
                    window_right[:] = hop_right[-fft_samples:]
                else:
                    window_left = np.roll(window_left, -hop_samples)
                    window_right = np.roll(window_right, -hop_samples)
                    window_left[-hop_samples:] = hop_left
                    window_right[-hop_samples:] = hop_right
                mono = (window_left + window_right) * 0.5

                vu_l = self._rms_to_level(np, hop_left)
                vu_r = self._rms_to_level(np, hop_right)
                bars = self._fft_bars(np, mono, active_backend, fft_context)
                fft_ms = (time.perf_counter() - t_fft0) * 1000.0

                samples_read += hop_samples
                decode_pos = start_pos + (samples_read / float(self._sample_rate))
                with self._lock:
                    self._decode_pos = decode_pos
                    mpv_pos = self._mpv_pos

                frames_emitted += 1
                now = time.perf_counter()
                elapsed = now - last_fps_t
                if elapsed >= 1.0:
                    current_fps = frames_emitted / elapsed
                    frames_emitted = 0
                    last_fps_t = now

                self.frame_ready.emit(
                    {
                        "bars": bars,
                        "vu_l": vu_l,
                        "vu_r": vu_r,
                        "decode_pos": decode_pos,
                        "mpv_pos": mpv_pos,
                        "sync_delta": decode_pos - mpv_pos if not stream_mode else 0.0,
                        "fft_ms": fft_ms,
                        "fps": current_fps,
                        "sample_rate": self._sample_rate,
                                "frame_samples": fft_samples,
                        "target_fps": target_fps,
                        "stream": stream_mode,
                        "backend": active_backend,
                        "requested_backend": requested_backend,
                        "backend_reason": str(fft_context.get("backend_reason", "")),
                        "source": source,
                    }
                )
        finally:
            with self._lock:
                if self._proc is proc:
                    self._proc = None
            try:
                if proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass
            try:
                if proc.stderr is not None:
                    err = proc.stderr.read(4096)
                    if err and not stop_event.is_set():
                        text = err.decode("utf-8", "ignore").strip()
                        if text:
                            self.log_line.emit("ffmpeg analyzer stderr: " + text.splitlines()[-1])
            except Exception:
                pass

    def _rms_to_level(self, np: Any, samples: Any) -> float:
        # Convert RMS to a normalized 0..1 VU level. -60 dB floor, 0 dB ceiling.
        rms = float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)) + 1e-12)
        db = 20.0 * math.log10(max(rms, 1e-12))
        return clamp((db + 60.0) / 60.0, 0.0, 1.0)

    def _fft_bars(self, np: Any, mono: Any, active_backend: str, fft_context: Dict[str, Any]) -> List[float]:
        # Rolling dB window adapts to the track's loudness so quiet recordings still
        # fill the display — same idea as the automatic gain on hardware analyzers.
        n = int(mono.size)
        if n <= 0:
            return [0.0 for _ in range(max(1, self._bars))]

        if (self._window_cache is None or len(self._window_cache) != n
                or getattr(self, "_cached_sr", None) != self._sample_rate):
            self._window_cache = np.hanning(n).astype(np.float32)
            self._bin_edges_cache = None
            self._cached_sr = self._sample_rate
            freqs = np.fft.rfftfreq(n, d=1.0 / self._sample_rate)
            low = 26.0
            high = min(19000.0, self._sample_rate / 2.0)
            edges = np.geomspace(low, high, self._bars + 1)
            bin_edges = []
            for lo, hi in zip(edges[:-1], edges[1:]):
                idx = np.where((freqs >= lo) & (freqs < hi))[0]
                if idx.size == 0:
                    idx = np.array([int(np.argmin(np.abs(freqs - lo)))])
                bin_edges.append(idx)
            self._bin_edges_cache = bin_edges

        # Strip DC offset so low-freq content doesn't inflate bin 0.
        mono = mono.astype(np.float32, copy=False)
        mono = mono - float(np.mean(mono))
        windowed = mono * self._window_cache

        if active_backend == "fftw" and "pyfftw_fft" in fft_context:
            _fftw_threads = min(4, max(1, os.cpu_count() or 2))
            spectrum = np.abs(fft_context["pyfftw_fft"].rfft(windowed, threads=_fftw_threads, planner_effort="FFTW_ESTIMATE"))
        elif active_backend in ("kissfft", "pfft") and "native_fft" in fft_context:
            try:
                spectrum = np.asarray(fft_context["native_fft"].rfft_magnitude(windowed.astype(np.float32), active_backend), dtype=np.float32)
            except Exception:
                spectrum = np.abs(np.fft.rfft(windowed))
        else:
            spectrum = np.abs(np.fft.rfft(windowed))

        coherent_gain = max(1e-9, float(np.sum(self._window_cache)) / float(n))
        spectrum = spectrum / max(1.0, float(n) * coherent_gain)

        db_values: List[float] = []
        for idx in self._bin_edges_cache:
            band = spectrum[idx]
            if getattr(band, "size", 0) == 0:
                db_values.append(-120.0)
                continue
            band_rms = float(np.sqrt(np.mean(np.square(band), dtype=np.float64)) + 1e-18)
            band_peak = float(np.max(band)) + 1e-18
            mag = max(band_rms * 0.82, band_peak * 0.42, 1e-18)
            db_values.append(20.0 * math.log10(mag))

        frame_peak_db = max(db_values) if db_values else -120.0
        if frame_peak_db < -108.0:
            self._display_peak_db = -72.0
            return [0.0 for _ in range(max(1, self._bars))]

        if frame_peak_db > self._display_peak_db:
            self._display_peak_db = (self._display_peak_db * 0.22) + (frame_peak_db * 0.78)
        else:
            self._display_peak_db = (self._display_peak_db * 0.94) + (frame_peak_db * 0.06)

        display_top = max(-52.0, min(2.0, self._display_peak_db + 8.0))
        display_floor = display_top - 62.0
        bars: List[float] = []
        for i, db in enumerate(db_values):
            level = (db - display_floor) / max(1.0, display_top - display_floor)
            tilt = 0.84 + 0.30 * (i / max(1, len(db_values) - 1))
            level = clamp(level * tilt, 0.0, 1.0)
            bars.append(float(math.pow(level, 0.58)))
        return bars


class AnalyzerPanel(QWidget):
    # Qt widget that draws the spectrum display. Gets frames from RealFftAnalyzer via
    # set_frame() and smooths them on a timer. All painting happens here, never in the
    # analyzer thread. The native C++ widget in native/ can replace this if you build it.

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._bar_count = 64
        self._bars = [0.0] * self._bar_count
        self._targets = [0.0] * self._bar_count
        self._peaks = [0.0] * self._bar_count
        self._vu_l = 0.0
        self._vu_r = 0.0
        self._vu_peak_l = 0.0
        self._vu_peak_r = 0.0
        self._state = "idle"
        self._status = "REAL FFT READY - WAITING FOR AUDIO"
        self._decode_pos = 0.0
        self._mpv_pos = 0.0
        self._sync_delta = 0.0
        self._fft_ms = 0.0
        self._fps = 0.0
        self._paint_ms = 0.0
        self._last_frame_ts = 0.0
        self._frames = 0
        self._target_peak = 0.0
        self._bar_peak = 0.0
        self._last_vu_energy = 0.0
        self._stream = False
        self._requested_backend = "auto"
        self._backend = "not-started"
        self._backend_reason = "not started"
        self._theme_name = DEFAULT_SPECTRUM_THEME
        self._visual_mode = DEFAULT_SPECTRUM_VISUAL_MODE
        self._render_fps = DEFAULT_RENDER_FPS
        self._graph_cache: Optional[QPixmap] = None
        self._graph_cache_key: Tuple[int, int, str] = (0, 0, "")
        self._ruler_cache: Optional[QPixmap] = None
        self._ruler_cache_key: Tuple[int, int, str] = (0, 0, "")
        self._vu_cache_l: Optional[QPixmap] = None
        self._vu_cache_l_key: Tuple = ()
        self._vu_cache_r: Optional[QPixmap] = None
        self._vu_cache_r_key: Tuple = ()
        self._freq_ticks_cache: Optional[list] = None
        self._phase = 0.0
        self._smooth_attack = 0.55
        self._smooth_release = 0.16
        self._peak_decay = 0.0105
        self._waterfall_history: List[List[float]] = []
        self._waterfall_max_rows = 120

        self._render_timer = QTimer(self)
        self._render_timer.setTimerType(Qt.PreciseTimer)
        self._render_timer.setInterval(max(1, int(1000 / self._render_fps)))
        self._render_timer.timeout.connect(self._tick_render)
        self._render_timer.start()

    def _theme(self) -> Dict[str, str]:
        key = SPECTRUM_THEME_ALIASES.get(self._theme_name, self._theme_name)
        return SPECTRUM_THEMES.get(key, SPECTRUM_THEMES[DEFAULT_SPECTRUM_THEME])

    def _c(self, key: str, alpha: Optional[int] = None) -> QColor:
        color = QColor(self._theme().get(key, "#ffffff"))
        if alpha is not None:
            color.setAlpha(max(0, min(255, int(alpha))))
        return color

    @Slot(str)
    def set_theme(self, theme_name: str) -> None:
        theme_name = SPECTRUM_THEME_ALIASES.get(str(theme_name), str(theme_name))
        if theme_name not in SPECTRUM_THEMES:
            theme_name = DEFAULT_SPECTRUM_THEME
        if theme_name != self._theme_name:
            self._theme_name = theme_name
            self._graph_cache = None
            self._graph_cache_key = (0, 0, "")
            self._ruler_cache = None
            self._vu_cache_l = None
            self._vu_cache_r = None
            self.update()

    @Slot(str)
    def set_visual_mode(self, mode: str) -> None:
        mode = SPECTRUM_VISUAL_ALIASES.get(str(mode or DEFAULT_SPECTRUM_VISUAL_MODE), str(mode or DEFAULT_SPECTRUM_VISUAL_MODE))
        valid = {key for key, _label in SPECTRUM_VISUAL_MODES}
        if mode not in valid:
            mode = DEFAULT_SPECTRUM_VISUAL_MODE
        if mode != self._visual_mode:
            self._visual_mode = mode
            self.update()

    @Slot(int)
    def set_bar_count(self, count: int) -> None:
        count = max(8, min(256, int(count)))
        if count != self._bar_count:
            self._bar_count = count
            self._bars = [0.0] * self._bar_count
            self._targets = [0.0] * self._bar_count
            self._peaks = [0.0] * self._bar_count
            self.update()

    @Slot(int)
    def set_render_fps(self, fps: int) -> None:
        try:
            fps = int(fps)
        except Exception:
            fps = DEFAULT_RENDER_FPS
        fps = max(15, min(60, fps))
        self._render_fps = fps
        self._render_timer.setInterval(max(1, int(round(1000.0 / float(fps)))))
        self.update()

    @Slot(str)
    def set_smooth_speed(self, preset: str) -> None:
        presets = {
            "fast":   (0.75, 0.30),
            "medium": (0.55, 0.16),
            "slow":   (0.30, 0.07),
        }
        self._smooth_attack, self._smooth_release = presets.get(str(preset), (0.55, 0.16))

    @Slot(str)
    def set_peak_decay(self, preset: str) -> None:
        presets = {
            "fast":   0.030,
            "medium": 0.0105,
            "hold":   0.003,
            "freeze": 0.0,
        }
        self._peak_decay = presets.get(str(preset), 0.0105)

    @Slot()
    def reset_peaks(self) -> None:
        self._peaks = [0.0] * self._bar_count
        self._vu_peak_l = 0.0
        self._vu_peak_r = 0.0
        self.update()

    @Slot(str)
    def set_state(self, state: str) -> None:
        self._state = state
        if state == "playing":
            self._status = "FFT ACTIVE - DECODED PCM ANALYZER"
        elif state == "paused":
            self._status = "PAUSED - FFT HOLD"
        elif state == "loading":
            self._status = "LOADING / RESYNC"
        elif state in ("stopped", "idle"):
            self._status = "REAL FFT READY - WAITING FOR AUDIO"
        else:
            self._status = state.upper()
        self.update()

    @Slot(str)
    def set_analyzer_status(self, status: str) -> None:
        if not status:
            return
        text = str(status).strip()
        low = text.lower()
        if low.startswith("requested-backend="):
            self._requested_backend = text.split("=", 1)[1].strip() or self._requested_backend
            self.update()
            return
        if low.startswith("active-backend="):
            parts = {}
            for chunk in text.split(";"):
                if "=" in chunk:
                    k, v = chunk.split("=", 1)
                    parts[k.strip().lower()] = v.strip()
            self._backend = parts.get("active-backend", self._backend)
            self._requested_backend = parts.get("requested", self._requested_backend)
            self._backend_reason = parts.get("reason", self._backend_reason)
            self._status = f"FFT ACTIVE: {self._backend.upper()}"
            self.update()
            return
        # Generic status string — keep it visible in the footer as-is.
        normalized = text.replace("-", " ").upper()
        if normalized in ("STARTING", "DECODING PCM", "STOPPED", "ENDED", "FFMPEG MISSING", "NUMPY MISSING"):
            self._status = f"ANALYZER: {normalized}"
        else:
            self._status = f"ANALYZER: {normalized}"
        self.update()

    @Slot(object)
    def set_frame(self, frame: object) -> None:
        if not isinstance(frame, dict):
            return
        bars = frame.get("bars")
        self._vu_l = clamp(float(frame.get("vu_l", 0.0)), 0.0, 1.0)
        self._vu_r = clamp(float(frame.get("vu_r", 0.0)), 0.0, 1.0)
        if isinstance(bars, list) and bars:
            if len(bars) != self._bar_count:
                self.set_bar_count(len(bars))
            targets = [clamp(float(x), 0.0, 1.0) for x in bars]
            # If we're still marked "loading" but a real frame arrived, switch to active.
            # mpv can stay in a transient loading state while audio is already decoding.
            if self._state in ("idle", "loading"):
                self._state = "playing"

            # Boost quiet signals so they fill the display — real data only, no fake bars.
            max_target = max(targets) if targets else 0.0
            vu_energy = max(self._vu_l, self._vu_r)
            self._last_vu_energy = vu_energy
            if 0.0 < max_target < 0.62 and vu_energy > 0.045:
                boost = min(180.0, max(1.0, 0.72 / max_target))
                targets = [clamp(x * boost, 0.0, 1.0) for x in targets]
                max_target = max(targets) if targets else max_target
            self._target_peak = max_target
            self._targets = targets
        self._decode_pos = safe_float(frame.get("decode_pos"), 0.0)
        self._mpv_pos = safe_float(frame.get("mpv_pos"), 0.0)
        self._sync_delta = safe_float(frame.get("sync_delta"), 0.0)
        self._fft_ms = safe_float(frame.get("fft_ms"), 0.0)
        self._fps = safe_float(frame.get("fps"), 0.0)
        self._stream = bool(frame.get("stream", False))
        self._backend = str(frame.get("backend", self._backend))
        self._requested_backend = str(frame.get("requested_backend", self._requested_backend))
        self._backend_reason = str(frame.get("backend_reason", self._backend_reason))
        self._status = "FFT FRAME LOCKED"
        self._last_frame_ts = time.perf_counter()
        self._frames += 1

    def _tick_render(self) -> None:
        now = time.perf_counter()
        self._phase = (self._phase + (1.0 / max(1.0, float(self._render_fps)))) % 100000.0
        fresh_frame = bool(self._last_frame_ts and (now - self._last_frame_ts) < 0.75)
        active_render = self._state in ("playing", "loading") or (fresh_frame and self._state not in ("paused", "stopped", "idle"))
        if active_render:
            for i, target in enumerate(self._targets):
                current = self._bars[i]
                alpha = self._smooth_attack if target > current else self._smooth_release
                current = current + (target - current) * alpha
                self._bars[i] = clamp(current, 0.0, 1.0)
                self._peaks[i] = current if current > self._peaks[i] else max(0.0, self._peaks[i] - self._peak_decay)
            self._bar_peak = max(self._bars) if self._bars else 0.0
            self._vu_peak_l = max(self._vu_l, self._vu_peak_l - 0.010)
            self._vu_peak_r = max(self._vu_r, self._vu_peak_r - 0.010)
        elif self._state == "paused":
            for i in range(self._bar_count):
                self._peaks[i] = max(self._bars[i], self._peaks[i] - 0.003)
            self._vu_peak_l = max(self._vu_l, self._vu_peak_l - 0.004)
            self._vu_peak_r = max(self._vu_r, self._vu_peak_r - 0.004)
        elif self._state in ("stopped", "idle"):
            for i in range(self._bar_count):
                self._bars[i] = max(0.0, self._bars[i] - 0.030)
                self._targets[i] = 0.0
                self._peaks[i] = max(0.0, self._peaks[i] - 0.030)
            self._vu_l = max(0.0, self._vu_l - 0.035)
            self._vu_r = max(0.0, self._vu_r - 0.035)
            self._vu_peak_l = max(0.0, self._vu_peak_l - 0.030)
            self._vu_peak_r = max(0.0, self._vu_peak_r - 0.030)
        self.update()

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        del event
        t0 = time.perf_counter()
        p = QPainter(self)
        r = self.rect().adjusted(1, 1, -1, -1)

        # Outer shell — antialiasing only for the two rounded rects that frame the deck
        p.fillRect(r, self._c("bg"))
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(self._c("border"), 1))
        p.setBrush(self._c("panel2"))
        p.drawRoundedRect(r, 10, 10)
        inner = r.adjusted(7, 7, -7, -7)
        p.setPen(QPen(self._c("grid", 90), 1))
        p.setBrush(self._c("panel"))
        p.drawRoundedRect(inner, 8, 8)
        p.setRenderHint(QPainter.Antialiasing, False)

        title_h = 34
        vu_w = 96
        footer_h = 48
        ruler_h = 36
        graph_w = max(180, inner.width() - (vu_w * 2) - 46)
        graph_h = max(120, inner.height() - title_h - footer_h - ruler_h - 18)
        graph = QRect(
            inner.left() + vu_w + 23,
            inner.top() + title_h + 10,
            graph_w,
            graph_h,
        )
        if graph.right() > inner.right() - vu_w - 14:
            graph.setRight(max(graph.left() + 160, inner.right() - vu_w - 14))
        ruler = QRect(graph.left(), graph.bottom() + 3, graph.width(), ruler_h)
        left_vu = QRect(inner.left() + 9, graph.top(), vu_w, graph.height())
        right_vu = QRect(inner.right() - vu_w - 9, graph.top(), vu_w, graph.height())

        p.setFont(QFont("DejaVu Sans Mono", 10, QFont.Bold))
        p.setPen(self._c("text"))
        p.drawText(inner.adjusted(12, 6, -12, -8), Qt.AlignTop | Qt.AlignLeft, "PYTUNE HF+ · REAL FFT SPECTRUM ANALYZER")
        p.setFont(QFont("DejaVu Sans Mono", 8))
        stale_ms = (time.perf_counter() - self._last_frame_ts) * 1000.0 if self._last_frame_ts else 0.0
        status = self._status
        if self._state == "playing" and stale_ms > 1250:
            status = "NO PCM FRAME - CHECK FFMPEG/ANALYZER"
        p.setPen(self._c("muted"))
        p.drawText(
            inner.adjusted(12, 7, -12, -8),
            Qt.AlignTop | Qt.AlignRight,
            f"{status}  ·  frames {self._frames:>7d}  ·  stale {stale_ms:>5.0f} ms  ·  {self._render_fps:>2d} fps",
        )

        self._draw_cached_grid(p, graph)
        self._draw_bars(p, graph)
        self._draw_frequency_ruler(p, ruler)
        self._draw_vu(p, left_vu, self._vu_l, self._vu_peak_l, "LEFT")
        self._draw_vu(p, right_vu, self._vu_r, self._vu_peak_r, "RIGHT")
        if self._bar_peak <= 0.01:
            self._draw_center_hint(p, graph, stale_ms)

        _mpv_t = format_seconds(self._mpv_pos).rjust(7)
        _dec_t = format_seconds(self._decode_pos).rjust(7)
        _delta = "  live-stm " if self._stream else f"Δ {self._sync_delta:+7.2f}s"
        perf = (
            f"mpv {_mpv_t} | dec {_dec_t} | {_delta} | "
            f"fft {self._fft_ms:6.2f} ms | anl {self._fps:4.1f} fps | paint {self._paint_ms:6.2f} ms | "
            f"tgt {self._target_peak:.3f} bar {self._bar_peak:.3f} vu {self._last_vu_energy:.3f} | "
            f"be {self._requested_backend}→{self._backend} | bars {self._bar_count:3d} | {self._render_fps:2d} fps | {self._backend_reason}"
        )
        p.setFont(QFont("DejaVu Sans Mono", 8))
        p.setPen(self._c("muted"))
        p.drawText(inner.adjusted(12, -footer_h + 8, -12, -7), Qt.AlignBottom | Qt.AlignLeft, perf)
        self._paint_ms = (time.perf_counter() - t0) * 1000.0
        p.end()

    def _freq_ratio(self, hz: float) -> float:
        low = 31.0
        high = 16000.0
        hz = clamp(float(hz), low, high)
        return (math.log10(hz) - math.log10(low)) / (math.log10(high) - math.log10(low))

    def _freq_ticks(self) -> List[Tuple[str, float, bool]]:
        if self._freq_ticks_cache is not None:
            return self._freq_ticks_cache
        major = [31, 63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]
        ticks: List[Tuple[str, float, bool]] = []
        for hz in major:
            label = f"{int(hz/1000)}K" if hz >= 1000 else str(hz)
            ticks.append((label, self._freq_ratio(float(hz)), True))
        for hz in [40, 50, 80, 100, 160, 200, 315, 400, 630, 800, 1250, 1600, 2500, 3150, 5000, 6300, 10000, 12500]:
            ticks.append(("", self._freq_ratio(float(hz)), False))
        self._freq_ticks_cache = ticks
        return ticks

    def _draw_cached_grid(self, p: QPainter, r: QRect) -> None:
        key = (max(1, r.width()), max(1, r.height()), self._theme_name)
        if self._graph_cache is None or self._graph_cache_key != key:
            pm = QPixmap(key[0], key[1])
            pm.fill(self._c("panel"))
            gp = QPainter(pm)
            gp.setRenderHint(QPainter.Antialiasing, True)
            rect = QRect(0, 0, key[0] - 1, key[1] - 1)

            gp.fillRect(rect, self._c("panel"))
            gp.setPen(QPen(self._c("border", 210), 1))
            gp.drawRect(rect)

            # Horizontal dB grid. Labels are kept faint so bars remain dominant.
            rows = [0, -6, -12, -24, -36, -48, -60]
            gp.setFont(QFont("DejaVu Sans Mono", 7))
            for db in rows:
                ratio = abs(db) / 60.0
                y = int(rect.top() + rect.height() * ratio)
                is_major = db in (0, -24, -48, -60)
                pen = QPen(self._c("grid_major" if is_major else "grid", 145 if is_major else 95), 1)
                gp.setPen(pen)
                gp.drawLine(rect.left(), y, rect.right(), y)
                label_alpha = 160 if is_major else 110
                gp.setPen(self._c("muted", label_alpha))
                gp.drawText(rect.left() + 5, y - 2, f"{db:>4}")
                gp.drawText(rect.right() - 28, y - 2, f"{db:>4}")
            # "dB" unit label in top corners so the scale is unambiguous.
            gp.setPen(self._c("muted", 110))
            gp.setFont(QFont("DejaVu Sans Mono", 6))
            gp.drawText(rect.left() + 5, rect.top() + 14, "dB")
            gp.drawText(rect.right() - 18, rect.top() + 14, "dB")

            # Logarithmic frequency grid aligned with the separate ruler below.
            for _label, ratio, is_major in self._freq_ticks():
                x = int(rect.left() + rect.width() * ratio)
                gp.setPen(QPen(self._c("grid_major" if is_major else "grid", 145 if is_major else 70), 1))
                gp.drawLine(x, rect.top(), x, rect.bottom())

            # Subtle baseline glow and top clip rail.
            gp.setPen(QPen(self._c("accent", 125), 1))
            gp.drawLine(rect.left(), rect.bottom() - 1, rect.right(), rect.bottom() - 1)
            gp.setPen(QPen(self._c("peak", 55), 1))
            gp.drawLine(rect.left(), rect.top() + 1, rect.right(), rect.top() + 1)
            gp.end()
            self._graph_cache = pm
            self._graph_cache_key = key
        p.drawPixmap(r.topLeft(), self._graph_cache)

        # Moving scan cursor is UI timing feedback, not generated spectrum data.
        if self._state in ("playing", "loading"):
            scan_x = r.left() + int((time.perf_counter() * 110) % max(1, r.width()))
            p.setPen(QPen(self._c("scan", 95), 1))
            p.drawLine(scan_x, r.top() + 2, scan_x, r.bottom() - 2)

    def _draw_frequency_ruler(self, p: QPainter, r: QRect) -> None:
        key = (r.width(), r.height(), self._theme_name)
        if self._ruler_cache is None or self._ruler_cache_key != key:
            pm = QPixmap(r.width(), r.height())
            gp = QPainter(pm)
            pm.fill(self._c("panel"))
            gp.setPen(QPen(self._c("border", 170), 1))
            gp.drawLine(0, 0, r.width(), 0)
            gp.drawLine(0, r.height() - 1, r.width(), r.height() - 1)
            gp.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
            for label, ratio, is_major in self._freq_ticks():
                x = int(r.width() * ratio)
                tick_h = 13 if is_major else 7
                alpha = 220 if is_major else 105
                gp.setPen(QPen(self._c("ruler", alpha), 1))
                gp.drawLine(x, 0, x, tick_h)
                if label:
                    tw = 28 if len(label) <= 3 else 34
                    gp.drawText(QRect(x - tw // 2, 14, tw, 14), Qt.AlignCenter, label)
            gp.setFont(QFont("DejaVu Sans Mono", 7))
            gp.setPen(self._c("muted", 170))
            gp.drawText(QRect(4, 1, 28, 12), Qt.AlignLeft | Qt.AlignVCenter, "Hz")
            gp.setPen(self._c("muted", 135))
            gp.drawText(QRect(4, 14, 44, 14), Qt.AlignLeft | Qt.AlignVCenter, "31")
            gp.drawText(QRect(0, 0, r.width() - 4, r.height()), Qt.AlignRight | Qt.AlignVCenter, "16k")
            gp.end()
            self._ruler_cache = pm
            self._ruler_cache_key = key
        p.drawPixmap(r.topLeft(), self._ruler_cache)

    def _draw_center_hint(self, p: QPainter, r: QRect, stale_ms: float) -> None:
        p.setFont(QFont("DejaVu Sans Mono", 11, QFont.Bold))
        if self._state == "playing" and stale_ms > 1250:
            text = "WAITING FOR REAL PCM FFT FRAME\ncheck log: FFmpeg / source decode / analyzer backend"
        elif self._state == "paused":
            text = "PAUSED - LAST REAL FRAME HELD"
        elif self._state in ("stopped", "idle"):
            text = "REAL SPECTRUM GRID READY"
        elif self._frames > 0 and self._last_vu_energy > 0.04:
            text = (
                "REAL PCM FRAMES ARRIVING - FFT DISPLAY ACTIVE\n"
                f"target={self._target_peak:.4f} bar={self._bar_peak:.4f} vu={self._last_vu_energy:.4f}"
            )
        else:
            text = f"{self._status}\nrequested {self._requested_backend} → active {self._backend}"
        p.setPen(self._c("muted", 190))
        p.drawText(r, Qt.AlignCenter, text)

    def _zone_color(self, zone_index: int, zones: int, alpha: Optional[int] = None) -> QColor:
        ratio = zone_index / max(1, zones - 1)
        if ratio >= 0.82:
            c = self._c("bar_hi")
        elif ratio >= 0.62:
            c = self._c("bar_mid")
        else:
            c = self._c("bar_lo")
        if alpha is not None:
            c.setAlpha(max(0, min(255, int(alpha))))
        return c

    def _draw_bars(self, p: QPainter, r: QRect) -> None:
        mode = self._visual_mode
        if mode == "dotmatrix":
            self._draw_matrix_leds(p, r, shape="rect")
            return
        if mode == "roundleds":
            self._draw_matrix_leds(p, r, shape="round")
            return
        if mode == "mirrorbars":
            self._draw_mirror_bars(p, r)
            return
        if mode == "neonpulse":
            self._draw_neon_pulse(p, r)
            return
        if mode == "rgbmatrix":
            self._draw_rgb_matrix(p, r)
            return
        if mode == "mirrorpulse":
            self._draw_mirror_pulse(p, r)
            return
        if mode == "radialhalo":
            self._draw_radial_halo(p, r)
            return
        if mode == "dawspectrum":
            self._draw_daw_spectrum(p, r)
            return
        if mode == "curvetrace":
            self._draw_curve_trace(p, r)
            return
        if mode == "vfdbars":
            self._draw_vfd_bars(p, r)
            return
        if mode == "splitstereo":
            self._draw_split_stereo_towers(p, r)
            return
        if mode == "laserfan":
            self._draw_laser_fan(p, r)
            return
        if mode == "glassbars":
            self._draw_glass_bars(p, r)
            return
        if mode == "pioneerfluoro":
            self._draw_pioneer_fluoro(p, r)
            return
        if mode == "technicsbridge":
            self._draw_technics_bridge(p, r)
            return
        if mode == "sonyes":
            self._draw_sony_es(p, r)
            return
        if mode == "kenwoodmatrix":
            self._draw_kenwood_matrix(p, r)
            return
        if mode == "boomboxwall":
            self._draw_boombox_wall(p, r)
            return
        if mode == "opposingbridge":
            self._draw_opposing_bridge(p, r)
            return
        if mode == "nightceiling":
            self._draw_nightclub_ceiling(p, r)
            return
        if mode == "waterfall":
            self._draw_waterfall(p, r)
            return

        # Default visual: segmented LED rack.
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        segs    = 24 if r.height() > 250 else 19
        seg_gap = 2
        seg_h   = max(2, int((usable_h - seg_gap * (segs - 1)) / segs))

        # Cache colors once — allocating QColor inside the bar loop is expensive
        trough  = self._c("vu_off", 170)
        c_lo    = self._c("bar_lo",  240)
        c_mid   = self._c("bar_mid", 240)
        c_hi    = self._c("bar_hi",  240)
        hi_thr  = int(segs * 0.82)
        mid_thr = int(segs * 0.62)
        pen_ch  = QPen(self._c("grid", 80), 1)
        pen_pk  = QPen(self._c("peak"), 1)
        pen_rl  = QPen(self._c("ruler", 190), 1)
        use_rr  = (bar_w >= 5)
        use_led = (bar_w >= 6 and seg_h >= 4)
        gloss   = QColor(255, 255, 255, 75)

        if use_rr:
            p.setRenderHint(QPainter.Antialiasing, True)

        for i, level in enumerate(self._bars):
            if i >= count:
                break
            x = x0 + i * (bar_w + gap)
            channel = QRect(x, r.top() + 4, bar_w, usable_h)
            p.setPen(pen_ch)
            p.setBrush(trough)
            if use_rr:
                p.drawRoundedRect(channel, 3, 3)
            else:
                p.fillRect(channel, trough)
            active = int(level * segs + 0.5)
            p.setPen(Qt.NoPen)
            for seg in range(active):
                y   = r.bottom() - 5 - (seg + 1) * seg_h - seg * seg_gap
                led = QRect(x + 1, y, max(1, bar_w - 2), seg_h)
                c   = c_hi if seg >= hi_thr else (c_mid if seg >= mid_thr else c_lo)
                p.setBrush(c)
                if use_led:
                    p.drawRoundedRect(led, 2, 2)
                    p.fillRect(QRect(led.left() + 1, led.top() + 1, max(1, led.width() - 2), 1), gloss)
                else:
                    p.fillRect(led, c)

        if use_rr:
            p.setRenderHint(QPainter.Antialiasing, False)

        p.setPen(pen_pk)
        for i in range(min(count, len(self._peaks))):
            x      = x0 + i * (bar_w + gap)
            peak_y = r.bottom() - 5 - int(self._peaks[i] * usable_h)
            p.drawLine(x, peak_y, x + bar_w, peak_y)
        p.setPen(pen_rl)
        p.drawLine(r.left() + 1, r.bottom() - 4, r.right() - 1, r.bottom() - 4)

    def _draw_matrix_leds(self, p: QPainter, r: QRect, shape: str = "rect") -> None:
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        rows   = 18 if r.height() < 250 else 24
        dot_gap = 2
        dot_h  = max(3, int((usable_h - dot_gap * (rows - 1)) / rows))

        # Cache colors once — allocating QColor inside the bar loop is expensive
        trough = self._c("vu_off", 135)
        c_pk   = self._c("peak", 220)
        c_lo   = self._c("bar_lo", 238)
        c_mid  = self._c("bar_mid", 238)
        c_hi   = self._c("bar_hi", 238)
        hi_thr = int(rows * 0.82)
        mid_thr = int(rows * 0.62)

        p.setPen(Qt.NoPen)
        use_aa = (shape == "round")
        if use_aa:
            p.setRenderHint(QPainter.Antialiasing, True)

        for i, level in enumerate(self._bars):
            if i >= count:
                break
            x = x0 + i * (bar_w + gap)
            active = int(level * rows + 0.5)
            for row in range(rows):
                y    = r.bottom() - 7 - (row + 1) * dot_h - row * dot_gap
                cell = QRect(x + 1, y, max(1, bar_w - 2), dot_h)
                c    = (c_hi if row >= hi_thr else (c_mid if row >= mid_thr else c_lo)) if row < active else trough
                p.setBrush(c)
                if shape == "round":
                    side = min(cell.width(), cell.height())
                    cx = cell.center().x()
                    cy = cell.center().y()
                    p.drawEllipse(QRect(cx - side // 2, cy - side // 2, side, side))
                elif cell.width() >= 5:
                    p.drawRoundedRect(cell, 2, 2)
                else:
                    p.fillRect(cell, c)

        if use_aa:
            p.setRenderHint(QPainter.Antialiasing, False)

        p.setPen(QPen(c_pk, 1))
        for i in range(min(count, len(self._peaks))):
            x = x0 + i * (bar_w + gap)
            peak_y = r.bottom() - 7 - int(self._peaks[i] * usable_h)
            p.drawLine(x, peak_y, x + bar_w, peak_y)
        p.setPen(QPen(self._c("ruler", 185), 1))
        p.drawLine(r.left() + 1, r.bottom() - 4, r.right() - 1, r.bottom() - 4)

    def _draw_mirror_bars(self, p: QPainter, r: QRect) -> None:
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        mid_y  = r.center().y()
        half_h = max(10, (usable_h // 2) - 4)
        # Cache colors once — allocating QColor inside the bar loop is expensive
        c_lo   = self._c("bar_lo")
        c_mid  = self._c("bar_mid")
        c_hi   = self._c("bar_hi")
        pen_pk = QPen(self._c("peak", 210), 1)
        use_rr = (bar_w >= 5)
        p.setPen(QPen(self._c("grid_major", 145), 1))
        p.drawLine(r.left() + 1, mid_y, r.right() - 1, mid_y)
        if use_rr:
            p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        for i, level in enumerate(self._bars):
            if i >= count:
                break
            x = x0 + i * (bar_w + gap)
            h = max(1, int(level * half_h))
            grad = QLinearGradient(x, mid_y, x, mid_y - h)
            grad.setColorAt(0.0,  c_lo)
            grad.setColorAt(0.60, c_mid)
            grad.setColorAt(1.0,  c_hi)
            br = QBrush(grad)
            up = QRect(x + 1, mid_y - h, max(1, bar_w - 2), h)
            dn = QRect(x + 1, mid_y,     max(1, bar_w - 2), h)
            p.setBrush(br)
            if use_rr:
                p.drawRoundedRect(up, 3, 3)
                p.drawRoundedRect(dn, 3, 3)
            else:
                p.fillRect(up, br)
                p.fillRect(dn, br)
        if use_rr:
            p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(pen_pk)
        for i in range(min(count, len(self._peaks))):
            x = x0 + i * (bar_w + gap)
            peak_h = int(self._peaks[i] * half_h)
            p.drawLine(x, mid_y - peak_h, x + bar_w, mid_y - peak_h)
            p.drawLine(x, mid_y + peak_h, x + bar_w, mid_y + peak_h)
        p.setPen(QPen(self._c("ruler", 190), 1))
        p.drawLine(r.left() + 1, r.bottom() - 4, r.right() - 1, r.bottom() - 4)

    def _color_for_level(self, level: float, alpha: Optional[int] = None) -> QColor:
        level = clamp(float(level), 0.0, 1.0)
        if level >= 0.78:
            c = self._c("bar_hi")
        elif level >= 0.48:
            c = self._c("bar_mid")
        else:
            c = self._c("bar_lo")
        if alpha is not None:
            c.setAlpha(max(0, min(255, int(alpha))))
        return c

    def _draw_neon_wave(self, p: QPainter, r: QRect) -> None:
        count = max(2, len(self._bars))
        usable_h = max(20, r.height() - 14)
        base_y = r.bottom() - 6
        path = QPainterPath()
        fill = QPainterPath()
        for i, level in enumerate(self._bars):
            x = r.left() + int((r.width() - 1) * (i / max(1, count - 1)))
            # Real FFT drives the contour; the phase only sweeps a tiny highlight over the same data.
            y = base_y - int((0.06 + level * 0.94) * usable_h)
            if i == 0:
                path.moveTo(x, y)
                fill.moveTo(x, base_y)
                fill.lineTo(x, y)
            else:
                path.lineTo(x, y)
                fill.lineTo(x, y)
        fill.lineTo(r.right(), base_y)
        fill.closeSubpath()
        grad = QLinearGradient(r.left(), r.top(), r.left(), r.bottom())
        grad.setColorAt(0.00, self._c("bar_hi", 130))
        grad.setColorAt(0.45, self._c("bar_mid", 80))
        grad.setColorAt(1.00, self._c("bar_lo", 22))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(fill)
        for width, alpha in ((7, 36), (4, 70), (2, 240)):
            p.setPen(QPen(self._c("bar_hi", alpha), width))
            p.drawPath(path)
        # traveling highlight dots derived from current bar heights
        p.setPen(Qt.NoPen)
        for k in range(9):
            idx = int(((self._phase * 9.0 + k * 0.117) % 1.0) * max(1, count - 1))
            level = self._bars[idx]
            x = r.left() + int((r.width() - 1) * (idx / max(1, count - 1)))
            y = base_y - int((0.06 + level * 0.94) * usable_h)
            c = self._color_for_level(level, 170)
            p.setBrush(c)
            p.drawEllipse(QPoint(x, y), 3, 3)
        p.setPen(QPen(self._c("ruler", 190), 1))
        p.drawLine(r.left() + 1, r.bottom() - 4, r.right() - 1, r.bottom() - 4)

    def _draw_radial_halo(self, p: QPainter, r: QRect) -> None:
        count = max(3, len(self._bars))
        cx = r.center().x()
        cy = r.center().y()
        base = max(22, min(r.width(), r.height()) // 5)
        span = max(28, min(r.width(), r.height()) // 3)
        # dim radial rails
        p.setPen(QPen(self._c("grid", 90), 1))
        for a in range(0, 360, 30):
            rad = math.radians(a)
            p.drawLine(cx, cy, cx + int(math.cos(rad) * (base + span)), cy + int(math.sin(rad) * (base + span)))
        path = QPainterPath()
        first = True
        for i, level in enumerate(self._bars + self._bars[:1]):
            angle = -math.pi / 2.0 + (i / count) * math.tau + self._phase * 0.08
            rr = base + span * clamp(level, 0.0, 1.0)
            x = cx + math.cos(angle) * rr
            y = cy + math.sin(angle) * rr
            if first:
                path.moveTo(x, y)
                first = False
            else:
                path.lineTo(x, y)
        p.setBrush(self._c("bar_lo", 26))
        p.setPen(QPen(self._c("bar_mid", 95), 3))
        p.drawPath(path)
        p.setPen(QPen(self._c("bar_hi", 230), 1))
        p.drawPath(path)
        for i, level in enumerate(self._bars):
            angle = -math.pi / 2.0 + (i / count) * math.tau + self._phase * 0.08
            rr0 = base
            rr1 = base + span * clamp(level, 0.0, 1.0)
            color = self._color_for_level(level, 210)
            p.setPen(QPen(color, 1.4))
            p.drawLine(cx + int(math.cos(angle) * rr0), cy + int(math.sin(angle) * rr0),
                       cx + int(math.cos(angle) * rr1), cy + int(math.sin(angle) * rr1))
        p.setPen(QPen(self._c("ruler", 185), 1))
        p.drawText(r.adjusted(8, 6, -8, -6), Qt.AlignTop | Qt.AlignLeft, "RADIAL FFT · LOG BANDS")

    def _draw_daw_spectrum(self, p: QPainter, r: QRect) -> None:
        """DAW-style spectrum: per-bar gradient (bar_lo→bar_hi) mapped to bar height, dB grid, Logic/Pro Tools look."""
        p.fillRect(r, self._c("panel"))
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        base_y = r.bottom() - 3

        # Cache colors once — allocating QColor inside the bar loop is expensive
        c_lo   = self._c("bar_lo")
        c_mid  = self._c("bar_mid")
        c_hi   = self._c("bar_hi")
        c_peak = self._c("peak", 230)
        trough = self._c("vu_off", 80)

        # Subtle dB grid — drawn first so bars paint over
        p.setFont(QFont("DejaVu Sans Mono", 6))
        for db in (-48, -36, -24, -12, -6):
            frac = clamp((db + 72) / 72.0, 0.0, 1.0)
            gy = base_y - int(frac * usable_h)
            p.setPen(QPen(self._c("grid", 55), 1))
            p.drawLine(r.left(), gy, r.right(), gy)
        p.setPen(self._c("muted", 110))
        for db in (-48, -24):
            frac = clamp((db + 72) / 72.0, 0.0, 1.0)
            gy = base_y - int(frac * usable_h)
            p.drawText(QRect(r.left() + 3, gy - 8, 26, 10), Qt.AlignLeft | Qt.AlignVCenter, f"{db:d}")

        pen_cap = QPen(c_hi, 1)
        p.setPen(Qt.NoPen)
        for i, level in enumerate(self._bars):
            if i >= count:
                break
            bx  = x0 + i * (bar_w + gap)
            bh  = max(2, int(level * usable_h))
            by  = base_y - bh
            p.fillRect(QRect(bx, base_y - usable_h, bar_w, usable_h), trough)
            grad = QLinearGradient(bx, base_y, bx, by)
            grad.setColorAt(0.0, c_lo)
            grad.setColorAt(0.6, c_mid)
            grad.setColorAt(1.0, c_hi)
            p.setBrush(QBrush(grad))
            p.drawRect(QRect(bx, by, bar_w, bh))
            p.setPen(pen_cap)
            p.drawLine(bx, by, bx + bar_w - 1, by)
            p.setPen(Qt.NoPen)

        # Peak hold dashes
        for i, pk in enumerate(self._peaks):
            if i >= count or pk < 0.01:
                continue
            bx = x0 + i * (bar_w + gap)
            py = base_y - int(pk * usable_h)
            p.setPen(QPen(c_peak, 1))
            p.drawLine(bx, py, bx + bar_w - 1, py)
            p.setPen(Qt.NoPen)

        p.setPen(QPen(self._c("border", 160), 1))
        p.drawRect(r.adjusted(0, 0, -1, -1))
        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(self._c("muted", 180))
        p.drawText(r.adjusted(8, 5, -8, -5), Qt.AlignTop | Qt.AlignLeft, "DAW SPECTRUM · REAL FFT")

    def _draw_curve_trace(self, p: QPainter, r: QRect) -> None:
        """Smooth frequency-response curve, FabFilter Pro-Q / Voxengo SPAN style.
        Fill uses lineTo (fast), stroke uses cubicTo (one pass only)."""
        p.fillRect(r, self._c("panel"))
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        if not self._bars:
            return

        base_y = float(r.bottom() - 3)

        # Subtle grid
        p.setPen(QPen(self._c("grid", 40), 1))
        for db in (-48, -36, -24, -12, -6):
            frac = clamp((db + 72) / 72.0, 0.0, 1.0)
            gy = r.bottom() - 3 - int(frac * usable_h)
            p.drawLine(r.left(), gy, r.right(), gy)

        # Point array — built once, used for both fill and stroke
        pts: list[tuple[float, float]] = []
        for i, level in enumerate(self._bars):
            if i >= count:
                break
            cx = float(x0 + i * (bar_w + gap) + bar_w // 2)
            cy = float(r.bottom() - 3 - int(level * usable_h))
            pts.append((cx, cy))
        if len(pts) < 2:
            return

        # Fill path — lineTo only (no bezier needed for the filled area)
        fill_path = QPainterPath()
        fill_path.moveTo(pts[0][0], base_y)
        for cx, cy in pts:
            fill_path.lineTo(cx, cy)
        fill_path.lineTo(pts[-1][0], base_y)
        fill_path.closeSubpath()

        c_hi = self._c("bar_hi"); c_hi.setAlpha(110)
        c_lo = self._c("bar_lo"); c_lo.setAlpha(20)
        grad = QLinearGradient(r.left(), r.top(), r.left(), r.bottom())
        grad.setColorAt(0.0, c_hi)
        grad.setColorAt(1.0, c_lo)
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawPath(fill_path)

        # Smooth curve in one pass — cubicTo avoids the jagged look of polyline
        stroke = QPainterPath()
        stroke.moveTo(pts[0][0], pts[0][1])
        for i in range(1, len(pts)):
            p0, p1 = pts[i - 1], pts[i]
            cpx = (p0[0] + p1[0]) * 0.5
            stroke.cubicTo(cpx, p0[1], cpx, p1[1], p1[0], p1[1])

        c_acc = self._c("accent"); c_acc.setAlpha(220)
        p.setPen(QPen(c_acc, 1.5))
        p.setBrush(Qt.NoBrush)
        p.drawPath(stroke)

        p.setPen(QPen(self._c("border", 140), 1))
        p.drawRect(r.adjusted(0, 0, -1, -1))
        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(self._c("muted", 175))
        p.drawText(r.adjusted(8, 5, -8, -5), Qt.AlignTop | Qt.AlignLeft, "FREQUENCY RESPONSE · REAL FFT")

    def _draw_vfd_bars(self, p: QPainter, r: QRect) -> None:
        """Classic segmented FFT meter: black background, lit segments only, green→yellow→red."""
        p.fillRect(r, QColor("#000000"))
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        base_y = r.bottom() - 3

        segs = 36 if r.height() > 240 else 22
        seg_h    = max(2, (usable_h - segs) // segs)
        seg_step = seg_h + 1

        C_LO   = QColor(0,   220,  60, 255)   # green
        C_MID  = QColor(220, 220,   0, 255)   # yellow
        C_HI   = QColor(255,  40,   0, 255)   # red
        C_PEAK = QColor(255, 255, 255, 255)   # white peak cap

        p.setPen(Qt.NoPen)
        for i, level in enumerate(self._bars):
            if i >= count:
                break
            bx  = x0 + i * (bar_w + gap)
            lit = int(level * segs)
            for s in range(lit):
                sy = base_y - (s + 1) * seg_step + 1
                if sy < r.top():
                    break
                frac = s / max(1, segs - 1)
                c = C_LO if frac < 0.65 else (C_MID if frac < 0.85 else C_HI)
                p.fillRect(QRect(bx, sy, bar_w, seg_h), c)

        # Peak caps
        for i, pk in enumerate(self._peaks):
            if i >= count or pk < 0.015:
                continue
            bx     = x0 + i * (bar_w + gap)
            pk_seg = int(pk * segs)
            sy     = base_y - (pk_seg + 1) * seg_step + 1
            if r.top() <= sy:
                p.fillRect(QRect(bx, sy, bar_w, seg_h), C_PEAK)

        p.setPen(QPen(QColor(40, 40, 40), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r.adjusted(0, 0, -1, -1))
        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(QColor(0, 180, 50))
        p.drawText(r.adjusted(8, 5, -8, -5), Qt.AlignTop | Qt.AlignLeft, "SEGMENT METER · REAL FFT")

    def _draw_neon_pulse(self, p: QPainter, r: QRect) -> None:
        """Club neon: thick bars on pure black, cyan/magenta/lime/red per frequency zone, soft glow."""
        p.fillRect(r, QColor("#000000"))
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        base_y = r.bottom() - 3

        # Pre-build zone colors and glow variants — OUTSIDE bar loop (no per-bar alloc)
        zone_colors = [
            QColor(0, 255, 255, 255),   # cyan   — sub/bass (0–30%)
            QColor(255, 0, 204, 255),   # magenta — low-mid (30–62%)
            QColor(170, 255, 0, 255),   # lime   — upper-mid (62–85%)
            QColor(255, 32, 32, 255),   # red    — clip zone (85–100%)
        ]
        zone_glow1 = [QColor(c.red(), c.green(), c.blue(), 38) for c in zone_colors]
        zone_glow2 = [QColor(c.red(), c.green(), c.blue(), 16) for c in zone_colors]
        c_white_pk = QColor(255, 255, 255, 255)

        p.setPen(Qt.NoPen)
        glow_extra = max(3, bar_w // 2)

        for i, level in enumerate(self._bars):
            if i >= count or level < 0.006:
                continue
            bx = x0 + i * (bar_w + gap)
            bh = max(2, int(level * usable_h))
            by = base_y - bh

            freq_frac = i / max(1, count - 1)
            zi = 0 if freq_frac < 0.30 else (1 if freq_frac < 0.62 else (2 if freq_frac < 0.85 else 3))

            # Outer + inner glow (pre-built colors, no alloc)
            p.fillRect(QRect(bx - glow_extra - 2, by - 2, bar_w + glow_extra * 2 + 4, bh + 4), zone_glow2[zi])
            p.fillRect(QRect(bx - glow_extra,     by,     bar_w + glow_extra * 2,     bh    ), zone_glow1[zi])
            # Solid bar
            p.fillRect(QRect(bx, by, bar_w, bh), zone_colors[zi])
            # Bright 2px top flare
            flare_a = min(255, 80 + int(160 * level))
            p.fillRect(QRect(bx, by, bar_w, 2), QColor(255, 255, 255, flare_a))

        # Peak hold — white tick
        for i, pk in enumerate(self._peaks):
            if i >= count or pk < 0.01:
                continue
            bx = x0 + i * (bar_w + gap)
            py = base_y - int(pk * usable_h)
            p.fillRect(QRect(bx, py, bar_w, 1), c_white_pk)

        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(QColor(255, 0, 204))
        p.drawText(r.adjusted(8, 5, -8, -5), Qt.AlignTop | Qt.AlignLeft, "NEON PULSE · REAL FFT")

    def _draw_rgb_matrix(self, p: QPainter, r: QRect) -> None:
        """RGB Frequency Rush: each bar is a unique hue (HSV wheel) — no per-bar gradient, just fast fillRect."""
        p.fillRect(r, QColor("#060606"))
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        base_y = r.bottom() - 3

        # Pre-build per-column hue colors once, outside the draw loop
        bar_colors: list[QColor] = []
        peak_colors: list[QColor] = []
        dim_colors:  list[QColor] = []
        for i in range(count):
            hue = int(300 * i / max(1, count - 1))
            bar_colors.append(QColor.fromHsv(hue, 255, 210, 255))
            peak_colors.append(QColor.fromHsv(hue, 180, 255, 240))
            dim_colors.append(QColor.fromHsv(hue, 200,  28, 255))  # very dark trough

        p.setPen(Qt.NoPen)
        c_white = QColor(255, 255, 255, 200)

        for i, level in enumerate(self._bars):
            if i >= count:
                break
            bx  = x0 + i * (bar_w + gap)
            bh  = max(2, int(level * usable_h))
            by  = base_y - bh
            # Dark trough slot
            p.fillRect(QRect(bx, base_y - usable_h, bar_w, usable_h), dim_colors[i])
            # Active bar — solid saturated hue, brightness scaled by level
            c = bar_colors[i]
            bright_val = int(80 + 130 * clamp(level * 1.8, 0.0, 1.0))
            bar_c = QColor.fromHsv(c.hsvHue(), 255, bright_val, 255)
            p.fillRect(QRect(bx, by, bar_w, bh), bar_c)
            # Bright 2px cap
            p.fillRect(QRect(bx, by, bar_w, 2), c_white)

        # Peak hold ticks
        for i, pk in enumerate(self._peaks):
            if i >= count or pk < 0.01:
                continue
            bx = x0 + i * (bar_w + gap)
            py = base_y - int(pk * usable_h)
            p.fillRect(QRect(bx, py, bar_w, 1), peak_colors[i])

        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(QColor.fromHsv(120, 240, 210))
        p.drawText(r.adjusted(8, 5, -8, -5), Qt.AlignTop | Qt.AlignLeft, "RGB FREQUENCY RUSH · REAL FFT")

    def _draw_mirror_pulse(self, p: QPainter, r: QRect) -> None:
        """Mirror Pulse Club: top+bottom mirrored bars, cyan up / magenta down, two shared gradients (not per-bar)."""
        p.fillRect(r, QColor("#03010a"))
        count, gap, bar_w, x0, _ = self._bar_geometry(r)
        half_h   = max(10, r.height() // 2 - 6)
        center_y = r.top() + r.height() // 2
        top_edge = center_y - half_h
        bot_edge = center_y + half_h

        # Two gradients built ONCE, spanning the full half-height — shared across all bars
        g_top = QLinearGradient(0, center_y, 0, top_edge)
        g_top.setColorAt(0.0, QColor(0, 229, 255, 40))
        g_top.setColorAt(1.0, QColor(0, 229, 255, 230))
        g_bot = QLinearGradient(0, center_y, 0, bot_edge)
        g_bot.setColorAt(0.0, QColor(255, 0, 170, 40))
        g_bot.setColorAt(1.0, QColor(255, 0, 170, 230))

        c_white = QColor(255, 255, 255, 200)

        # Top half — all bars in one pass with shared gradient
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(g_top))
        for i, level in enumerate(self._bars):
            if i >= count:
                break
            bx = x0 + i * (bar_w + gap)
            bh = max(2, int(level * half_h))
            p.drawRect(QRect(bx, center_y - bh, bar_w, bh))

        # Bottom half
        p.setBrush(QBrush(g_bot))
        for i, level in enumerate(self._bars):
            if i >= count:
                break
            bx = x0 + i * (bar_w + gap)
            bh = max(2, int(level * half_h))
            p.drawRect(QRect(bx, center_y, bar_w, bh))

        # Edge flares (single color, no per-bar QColor)
        p.setBrush(Qt.NoBrush)
        for i, level in enumerate(self._bars):
            if i >= count or level < 0.01:
                continue
            bx = x0 + i * (bar_w + gap)
            bh = max(2, int(level * half_h))
            p.fillRect(QRect(bx, center_y - bh, bar_w, 2), c_white)
            p.fillRect(QRect(bx, center_y + bh - 2, bar_w, 2), c_white)

        # Center divider
        p.setPen(QPen(c_white, 1))
        p.drawLine(r.left(), center_y, r.right(), center_y)

        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(QColor(0, 229, 255))
        p.drawText(r.adjusted(8, 5, r.width() // 2, -5), Qt.AlignTop | Qt.AlignLeft, "MIRROR PULSE")
        p.setPen(QColor(255, 0, 170))
        p.drawText(r.adjusted(0, 5, -8, -5), Qt.AlignTop | Qt.AlignRight, "REAL FFT")

    def _draw_split_stereo_towers(self, p: QPainter, r: QRect) -> None:
        # Uses the real FFT bars and live L/R VU values to give each side a different energy envelope.
        mid = r.center().x()
        left = QRect(r.left(), r.top(), max(20, (r.width() // 2) - 4), r.height())
        right = QRect(mid + 4, r.top(), max(20, r.right() - mid - 4), r.height())
        old_bars = list(self._bars)
        try:
            self._bars = [clamp(v * (0.82 + self._vu_l * 0.34), 0.0, 1.0) for v in reversed(old_bars)]
            self._draw_glass_bars(p, left)
            self._bars = [clamp(v * (0.82 + self._vu_r * 0.34), 0.0, 1.0) for v in old_bars]
            self._draw_glass_bars(p, right)
        finally:
            self._bars = old_bars
        p.setPen(QPen(self._c("grid_major", 150), 1))
        p.drawLine(mid, r.top() + 2, mid, r.bottom() - 5)
        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(self._c("muted", 190))
        p.drawText(left.adjusted(6, 4, -6, -4), Qt.AlignTop | Qt.AlignLeft, "LEFT WEIGHTED")
        p.drawText(right.adjusted(6, 4, -6, -4), Qt.AlignTop | Qt.AlignRight, "RIGHT WEIGHTED")

    def _draw_laser_fan(self, p: QPainter, r: QRect) -> None:
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        origin = QPoint(r.center().x(), r.bottom() - 5)
        p.setPen(Qt.NoPen)
        for i, level in enumerate(self._bars):
            x = x0 + i * (bar_w + gap) + bar_w // 2
            y = r.bottom() - 8 - int(level * usable_h)
            c = self._color_for_level(level, int(35 + 175 * level))
            p.setPen(QPen(c, 1.0 + 2.2 * level))
            p.drawLine(origin, QPoint(x, y))
        # small endpoint LEDs
        p.setPen(Qt.NoPen)
        for i, level in enumerate(self._bars):
            if level < 0.03:
                continue
            x = x0 + i * (bar_w + gap) + bar_w // 2
            y = r.bottom() - 8 - int(level * usable_h)
            c = self._color_for_level(level, 230)
            p.setBrush(c)
            p.drawEllipse(QPoint(x, y), 2, 2)
        p.setPen(QPen(self._c("ruler", 190), 1))
        p.drawLine(r.left() + 1, r.bottom() - 4, r.right() - 1, r.bottom() - 4)

    def _bar_geometry(self, r: QRect) -> Tuple[int, int, int, int, int]:
        count = max(1, self._bar_count)
        gap = 3 if count <= 64 else 2 if count <= 128 else 1
        bar_w = max(2, int((r.width() - gap * (count - 1)) / count))
        usable_w = count * bar_w + (count - 1) * gap
        x0 = r.left() + max(0, (r.width() - usable_w) // 2)
        usable_h = r.height() - 10
        return count, gap, bar_w, x0, usable_h

    def _draw_glass_bars(self, p: QPainter, r: QRect) -> None:
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        # Cache colors once — allocating QColor inside the bar loop is expensive
        trough  = self._c("vu_off", 125)
        c_lo    = self._c("bar_lo")
        c_mid   = self._c("bar_mid")
        c_hi    = self._c("bar_hi")
        c_gloss = self._c("peak", 36)
        pen_ch  = QPen(self._c("grid", 100), 1)
        pen_pk  = QPen(self._c("peak"), 1)
        pen_rl  = QPen(self._c("ruler", 190), 1)
        use_rr  = (bar_w >= 5)
        if use_rr:
            p.setRenderHint(QPainter.Antialiasing, True)
        for i, level in enumerate(self._bars):
            if i >= count:
                break
            x = x0 + i * (bar_w + gap)
            h = max(1, int(level * usable_h))
            y = r.bottom() - 5 - h
            channel = QRect(x, r.top() + 4, bar_w, usable_h)
            p.setPen(pen_ch)
            p.setBrush(trough)
            if use_rr:
                p.drawRoundedRect(channel, 3, 3)
            else:
                p.fillRect(channel, trough)
            if h > 1:
                active = QRect(x + 1, y, max(1, bar_w - 2), h)
                grad = QLinearGradient(active.left(), active.bottom(), active.left(), active.top())
                grad.setColorAt(0.00, c_lo)
                grad.setColorAt(0.62, c_mid)
                grad.setColorAt(1.00, c_hi)
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(grad))
                if use_rr:
                    p.drawRoundedRect(active, 3, 3)
                else:
                    p.fillRect(active, QBrush(grad))
                if bar_w >= 6:
                    p.fillRect(QRect(active.left() + 1, active.top() + 1, max(1, active.width() // 3), active.height() - 2), c_gloss)
        if use_rr:
            p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(pen_pk)
        for i in range(min(count, len(self._peaks))):
            x = x0 + i * (bar_w + gap)
            peak_y = r.bottom() - 5 - int(self._peaks[i] * usable_h)
            p.drawLine(x, peak_y, x + bar_w, peak_y)
        p.setPen(pen_rl)
        p.drawLine(r.left() + 1, r.bottom() - 4, r.right() - 1, r.bottom() - 4)

    def _draw_dot_matrix(self, p: QPainter, r: QRect) -> None:
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        rows   = 18 if r.height() < 250 else 24
        dot_h  = max(2, int((usable_h - rows) / rows))
        radius = max(1, min(4, dot_h // 2))
        hi_thr  = int(rows * 0.82)
        mid_thr = int(rows * 0.62)
        # Pre-cache all colors once
        c_hi  = self._c("bar_hi",  235)
        c_mid = self._c("bar_mid", 235)
        c_lo  = self._c("bar_lo",  235)
        c_off = self._c("vu_off",   95)
        pen_pk = QPen(self._c("peak", 210), 1)
        p.setPen(Qt.NoPen)
        p.setRenderHint(QPainter.Antialiasing, True)
        for i, level in enumerate(self._bars):
            if i >= count:
                break
            cx = x0 + i * (bar_w + gap) + max(1, bar_w // 2)
            active = int(level * rows + 0.5)
            for row in range(rows):
                cy = r.bottom() - 7 - row * (dot_h + 1)
                c  = (c_hi if row >= hi_thr else (c_mid if row >= mid_thr else c_lo)) if row < active else c_off
                p.setBrush(c)
                p.drawEllipse(QPoint(cx, cy), radius, radius)
        p.setRenderHint(QPainter.Antialiasing, False)
        p.setPen(pen_pk)
        for i in range(min(count, len(self._peaks))):
            cx = x0 + i * (bar_w + gap) + max(1, bar_w // 2)
            peak_y = r.bottom() - 7 - int(self._peaks[i] * usable_h)
            p.drawLine(cx - radius - 1, peak_y, cx + radius + 1, peak_y)

    def _draw_trace_spectrum(self, p: QPainter, r: QRect) -> None:
        count = max(1, self._bar_count)
        usable_h = r.height() - 12
        path = QPainterPath()
        fill = QPainterPath()
        for i, level in enumerate(self._bars):
            x = r.left() + int((r.width() - 1) * (i / max(1, count - 1)))
            y = r.bottom() - 6 - int(level * usable_h)
            if i == 0:
                path.moveTo(x, y)
                fill.moveTo(x, r.bottom() - 5)
                fill.lineTo(x, y)
            else:
                path.lineTo(x, y)
                fill.lineTo(x, y)
        fill.lineTo(r.right(), r.bottom() - 5)
        fill.closeSubpath()
        grad = QLinearGradient(r.left(), r.top(), r.left(), r.bottom())
        hi = self._c("bar_hi", 110)
        lo = self._c("bar_lo", 25)
        grad.setColorAt(0.0, hi)
        grad.setColorAt(1.0, lo)
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(fill)
        p.setPen(QPen(self._c("bar_hi"), 2))
        p.drawPath(path)
        p.setPen(QPen(self._c("peak", 175), 1))
        for i, peak in enumerate(self._peaks):
            x = r.left() + int((r.width() - 1) * (i / max(1, count - 1)))
            y = r.bottom() - 6 - int(peak * usable_h)
            p.drawPoint(x, y)
        p.setPen(QPen(self._c("ruler", 190), 1))
        p.drawLine(r.left() + 1, r.bottom() - 4, r.right() - 1, r.bottom() - 4)


    def _draw_pioneer_fluoro(self, p: QPainter, r: QRect) -> None:
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        p.fillRect(r, self._c("panel", 210))
        for i, level in enumerate(self._bars):
            x = x0 + i * (bar_w + gap)
            h = max(1, int(level * usable_h))
            y = r.bottom() - 6 - h
            glow = self._color_for_level(level, int(40 + level * 120))
            p.setPen(Qt.NoPen)
            p.setBrush(glow)
            if bar_w >= 4:
                p.drawRoundedRect(QRect(x - 1, y - 2, bar_w + 2, h + 4), 3, 3)
            active = QRect(x, y, max(1, bar_w), h)
            grad = QLinearGradient(active.left(), active.bottom(), active.left(), active.top())
            grad.setColorAt(0.00, self._c("bar_lo"))
            grad.setColorAt(0.55, self._c("bar_mid"))
            grad.setColorAt(1.00, self._c("bar_hi"))
            p.setBrush(QBrush(grad))
            if bar_w >= 5:
                p.drawRoundedRect(active, 3, 3)
            else:
                p.drawRect(active)
            # Fluorescent scanline cuts.
            p.setPen(QPen(self._c("panel", 90), 1))
            step = 6
            yy = active.bottom() - step
            while yy > active.top():
                p.drawLine(active.left(), yy, active.right(), yy)
                yy -= step
            peak_y = r.bottom() - 6 - int(self._peaks[i] * usable_h)
            p.setPen(QPen(self._c("peak", 235), 1))
            p.drawLine(x, peak_y, x + bar_w, peak_y)
        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(self._c("muted", 190))
        p.drawText(r.adjusted(8, 6, -8, -6), Qt.AlignTop | Qt.AlignLeft, "PIONEER FLUORO · LOG FFT")

    def _draw_technics_bridge(self, p: QPainter, r: QRect) -> None:
        count = max(1, len(self._bars))
        center_y = r.center().y()
        rail_h = max(7, min(18, r.height() // 18))
        gap = 2
        bar_w = max(2, int((r.width() - gap * (count - 1)) / count))
        usable_w = count * bar_w + (count - 1) * gap
        x0 = r.left() + max(0, (r.width() - usable_w) // 2)
        p.setPen(QPen(self._c("grid_major", 120), 1))
        p.drawLine(r.left() + 8, center_y, r.right() - 8, center_y)
        for i, level in enumerate(self._bars):
            x = x0 + i * (bar_w + gap)
            reach = int(level * max(8, r.height() // 2 - 12))
            c = self._color_for_level(level, 235 if level > 0.08 else 120)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            if reach > 0:
                p.drawRoundedRect(QRect(x, center_y - reach, bar_w, reach), 2, 2)
                p.drawRoundedRect(QRect(x, center_y + 1, bar_w, reach), 2, 2)
            p.setBrush(self._c("vu_off", 95))
            p.drawRect(QRect(x, center_y - rail_h // 2, bar_w, rail_h))
            peak = int(self._peaks[i] * max(8, r.height() // 2 - 12))
            p.setPen(QPen(self._c("peak", 220), 1))
            p.drawLine(x, center_y - peak, x + bar_w, center_y - peak)
            p.drawLine(x, center_y + peak, x + bar_w, center_y + peak)
        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(self._c("muted", 190))
        p.drawText(r.adjusted(8, 6, -8, -6), Qt.AlignTop | Qt.AlignLeft, "TECHNICS OPPOSING LED BRIDGE")

    def _draw_sony_es(self, p: QPainter, r: QRect) -> None:
        # Polished ES-style glass analyzer: deep troughs, bright bars, restrained highlights.
        inner = r.adjusted(4, 4, -4, -4)
        grad = QLinearGradient(inner.left(), inner.top(), inner.left(), inner.bottom())
        grad.setColorAt(0.0, self._c("panel2", 230))
        grad.setColorAt(0.45, self._c("panel", 245))
        grad.setColorAt(1.0, self._c("panel2", 180))
        p.setPen(QPen(self._c("border", 170), 1))
        p.setBrush(QBrush(grad))
        p.drawRoundedRect(inner, 8, 8)
        self._draw_glass_bars(p, inner.adjusted(8, 8, -8, -8))
        p.setPen(Qt.NoPen)
        p.setBrush(self._c("peak", 22))
        p.drawRoundedRect(QRect(inner.left()+8, inner.top()+8, inner.width()-16, max(12, inner.height()//5)), 6, 6)
        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(self._c("muted", 190))
        p.drawText(inner.adjusted(10, 8, -10, -8), Qt.AlignTop | Qt.AlignLeft, "SONY ES GLASS ANALYZER")

    def _draw_kenwood_matrix(self, p: QPainter, r: QRect) -> None:
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        rows = 30 if r.height() >= 260 else 22
        dot_w = max(2, min(7, bar_w - 1))
        dot_h = max(2, int((usable_h - rows) / rows))
        for i, level in enumerate(self._bars):
            x = x0 + i * (bar_w + gap) + max(0, (bar_w - dot_w) // 2)
            active = int(level * rows + 0.5)
            for row in range(rows):
                y = r.bottom() - 7 - row * (dot_h + 1)
                if row < active:
                    c = self._color_for_level(row / max(1, rows - 1), 240)
                else:
                    c = self._c("vu_off", 90)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(QRect(x, y, dot_w, dot_h), 1, 1)
        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(self._c("muted", 190))
        p.drawText(r.adjusted(8, 6, -8, -6), Qt.AlignTop | Qt.AlignLeft, "KENWOOD DOT MATRIX · PEAK HOLD")

    def _draw_boombox_wall(self, p: QPainter, r: QRect) -> None:
        count = max(1, len(self._bars))
        cols = min(count, max(16, r.width() // 14))
        rows = max(6, min(12, r.height() // 28))
        cell_w = max(4, r.width() // cols)
        cell_h = max(4, (r.height() - 18) // rows)
        for col in range(cols):
            src = int(col * count / cols)
            level = self._bars[src]
            active_rows = int(level * rows + 0.5)
            for row in range(rows):
                x = r.left() + col * cell_w + 2
                y = r.bottom() - 8 - (row + 1) * cell_h
                rect = QRect(x, y, max(2, cell_w - 4), max(2, cell_h - 3))
                if row < active_rows:
                    c = self._color_for_level((row + 1) / rows, 230)
                else:
                    c = self._c("vu_off", 100)
                p.setPen(QPen(self._c("grid", 95), 1))
                p.setBrush(c)
                p.drawRoundedRect(rect, 3, 3)
        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(self._c("muted", 190))
        p.drawText(r.adjusted(8, 6, -8, -6), Qt.AlignTop | Qt.AlignLeft, "BOOMBOX BLINKER WALL · GROUPED FFT")

    def _draw_opposing_bridge(self, p: QPainter, r: QRect) -> None:
        upper = QRect(r.left(), r.top(), r.width(), max(20, r.height() // 2 - 3))
        lower = QRect(r.left(), r.center().y() + 3, r.width(), max(20, r.height() // 2 - 3))
        old = list(self._bars)
        try:
            self._bars = list(reversed(old))
            self._draw_matrix_leds(p, upper, shape="rect")
            self._bars = old
            self._draw_matrix_leds(p, lower, shape="round")
        finally:
            self._bars = old
        p.setPen(QPen(self._c("grid_major", 155), 1))
        p.drawLine(r.left()+4, r.center().y(), r.right()-4, r.center().y())
        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(self._c("muted", 190))
        p.drawText(r.adjusted(8, 6, -8, -6), Qt.AlignTop | Qt.AlignLeft, "OPPOSING BRIDGE METERS")

    def _draw_nightclub_ceiling(self, p: QPainter, r: QRect) -> None:
        count, gap, bar_w, x0, usable_h = self._bar_geometry(r)
        rig_y = r.top() + max(16, r.height() // 9)
        p.setPen(QPen(self._c("border", 180), 3))
        p.drawLine(r.left()+12, rig_y, r.right()-12, rig_y)
        fixtures = 7
        for f in range(fixtures):
            fx = r.left() + int((f + 0.5) * r.width() / fixtures)
            p.setPen(Qt.NoPen)
            p.setBrush(self._c("panel2", 230))
            p.drawRoundedRect(QRect(fx-9, rig_y-7, 18, 14), 4, 4)
        stride = max(1, count // fixtures)
        for f in range(fixtures):
            idx = min(count-1, f * stride)
            level = max(self._bars[idx:idx+stride] or [0.0])
            fx = r.left() + int((f + 0.5) * r.width() / fixtures)
            target_x = x0 + idx * (bar_w + gap) + bar_w // 2
            target_y = r.bottom() - 8 - int(level * (usable_h - 20))
            c = self._color_for_level(level, int(45 + 170 * level))
            p.setPen(QPen(c, 1.2 + 2.4 * level))
            p.drawLine(QPoint(fx, rig_y+8), QPoint(target_x, target_y))
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawEllipse(QPoint(target_x, target_y), 3, 3)
        # ground LEDs from same real FFT vector
        for i, level in enumerate(self._bars):
            if i % max(1, count // 48) != 0:
                continue
            x = x0 + i * (bar_w + gap)
            h = max(1, int(level * (usable_h // 3)))
            p.setPen(Qt.NoPen)
            p.setBrush(self._color_for_level(level, 210))
            p.drawRect(QRect(x, r.bottom()-6-h, max(1, bar_w), h))
        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(self._c("muted", 190))
        p.drawText(r.adjusted(8, 6, -8, -6), Qt.AlignTop | Qt.AlignLeft, "NIGHTCLUB CEILING SWEEP · REAL FFT BEAMS")

    def _draw_waterfall(self, p: QPainter, r: QRect) -> None:
        bars = self._bars
        if bars and self._state == "active":
            self._waterfall_history.append(list(bars))
            if len(self._waterfall_history) > self._waterfall_max_rows:
                self._waterfall_history.pop(0)

        history = self._waterfall_history
        if not history:
            p.fillRect(r, self._c("bg"))
            p.setPen(self._c("muted", 130))
            p.setFont(QFont("DejaVu Sans Mono", 9))
            p.drawText(r, Qt.AlignCenter, "WATERFALL CINEMA\nwaiting for audio…")
            return

        n_rows = len(history)
        n_cols = len(history[0]) if history else 1
        row_h = max(1, r.height() // max(1, self._waterfall_max_rows))
        col_w = max(1, r.width() // max(1, n_cols))
        bg = self._c("bg")
        p.fillRect(r, bg)

        c_lo  = self._c("bar_lo")
        c_mid = self._c("bar_mid")
        c_hi  = self._c("bar_hi")
        c_pk  = self._c("peak")

        draw_top = r.bottom() - n_rows * row_h
        for row_i, row in enumerate(history):
            y = r.bottom() - (row_i + 1) * row_h
            for col_i, level in enumerate(row):
                if level < 0.04:
                    continue
                x = r.left() + col_i * col_w
                if level < 0.40:
                    frac = level / 0.40
                    cr = int(c_lo.red()   + frac * (c_mid.red()   - c_lo.red()))
                    cg = int(c_lo.green() + frac * (c_mid.green() - c_lo.green()))
                    cb = int(c_lo.blue()  + frac * (c_mid.blue()  - c_lo.blue()))
                    ca = int(60 + level * 160)
                elif level < 0.78:
                    frac = (level - 0.40) / 0.38
                    cr = int(c_mid.red()   + frac * (c_hi.red()   - c_mid.red()))
                    cg = int(c_mid.green() + frac * (c_hi.green() - c_mid.green()))
                    cb = int(c_mid.blue()  + frac * (c_hi.blue()  - c_mid.blue()))
                    ca = int(130 + level * 100)
                else:
                    frac = min(1.0, (level - 0.78) / 0.22)
                    cr = int(c_hi.red()   + frac * (c_pk.red()   - c_hi.red()))
                    cg = int(c_hi.green() + frac * (c_pk.green() - c_hi.green()))
                    cb = int(c_hi.blue()  + frac * (c_pk.blue()  - c_hi.blue()))
                    ca = 220
                p.fillRect(QRect(x, y, col_w, row_h), QColor(cr, cg, cb, ca))

        # current-row live bar overlay at bottom
        if history:
            live = history[-1]
            live_y = r.bottom() - row_h
            for col_i, level in enumerate(live):
                if level < 0.01:
                    continue
                x = r.left() + col_i * col_w
                h = max(1, int(level * row_h * 3))
                p.fillRect(QRect(x, live_y - h + row_h, col_w, h),
                           QColor(255, 255, 255, int(40 + level * 160)))

        p.setFont(QFont("DejaVu Sans Mono", 7, QFont.Bold))
        p.setPen(self._c("muted", 180))
        p.drawText(r.adjusted(8, 6, -8, -6), Qt.AlignTop | Qt.AlignLeft, "WATERFALL CINEMA · REAL FFT HISTORY")

    def _draw_vu(self, p: QPainter, r: QRect, value: float, peak: float, label: str) -> None:
        is_left = label.upper().startswith("LEFT")
        header_h = 20
        db_col_w = 25
        meter_top    = r.top() + header_h + 3
        meter_bottom = r.bottom() - 8
        meter_h      = max(20, meter_bottom - meter_top)
        if is_left:
            meter    = QRect(r.left() + 6, meter_top, max(12, r.width() - db_col_w - 12), meter_h)
            db_rect_x = meter.right() + 2
        else:
            meter    = QRect(r.left() + db_col_w + 4, meter_top, max(12, r.width() - db_col_w - 12), meter_h)
            db_rect_x = r.left() + 2

        # --- Static chrome: cached pixmap (border, header, dB ruler) ---
        cache_key = (r.width(), r.height(), self._theme_name, label)
        chrome = self._vu_cache_l if is_left else self._vu_cache_r
        chrome_key = self._vu_cache_l_key if is_left else self._vu_cache_r_key
        if chrome is None or chrome_key != cache_key:
            pm = QPixmap(r.width(), r.height())
            pm.fill(Qt.transparent)
            gp = QPainter(pm)
            gp.setRenderHint(QPainter.Antialiasing, True)
            # Outer rounded frame
            lm = QRect(0, 0, r.width(), r.height())
            gp.setPen(QPen(self._c("border", 190), 1))
            gp.setBrush(self._c("panel"))
            gp.drawRoundedRect(lm, 5, 5)
            gp.setRenderHint(QPainter.Antialiasing, False)
            # Channel letter
            gp.setFont(QFont("DejaVu Sans Mono", 8, QFont.Bold))
            gp.setPen(self._c("text"))
            gp.drawText(QRect(0, 2, r.width(), 16), Qt.AlignCenter, "L" if is_left else "R")
            # "dB" unit label
            gp.setFont(QFont("DejaVu Sans Mono", 6))
            gp.setPen(self._c("muted", 170))
            ldb_rect_x = db_rect_x - r.left()
            lmeter_top = meter_top - r.top()
            lmeter_h   = meter_h
            gp.drawText(QRect(ldb_rect_x, 2, db_col_w, 12),
                        (Qt.AlignLeft if is_left else Qt.AlignRight) | Qt.AlignVCenter, "dB")
            # dB ruler ticks + labels
            c_major = self._c("grid_major", 180)
            c_minor = self._c("grid", 120)
            c_txt_ep = self._c("muted", 210)
            c_txt_mn = self._c("muted", 160)
            for db in (0, -12, -24, -36, -48, -60):
                ratio = abs(db) / 60.0
                y = lmeter_top + int(lmeter_h * ratio)
                is_ep = db in (0, -60)
                tick_len = 6 if is_ep else 4
                gp.setPen(c_major if is_ep else c_minor)
                lmx = meter.left() - r.left()
                lmr = meter.right() - r.left()
                if is_left:
                    gp.drawLine(lmr - tick_len, y, lmr, y)
                else:
                    gp.drawLine(lmx, y, lmx + tick_len, y)
                gp.setPen(c_txt_ep if is_ep else c_txt_mn)
                gp.drawText(QRect(ldb_rect_x, y - 7, db_col_w, 12),
                            (Qt.AlignLeft if is_left else Qt.AlignRight) | Qt.AlignVCenter, f"{db:>4d}")
            # 0 dB reference line
            gp.setPen(QPen(self._c("bar_hi", 120), 1))
            gp.drawLine(meter.left() - r.left(), lmeter_top, meter.right() - r.left(), lmeter_top)
            gp.end()
            chrome = pm
            if is_left:
                self._vu_cache_l, self._vu_cache_l_key = pm, cache_key
            else:
                self._vu_cache_r, self._vu_cache_r_key = pm, cache_key

        p.drawPixmap(r.topLeft(), chrome)

        # --- Live segments (only the bar fill changes each frame) ---
        segs  = 28
        gap   = 2
        seg_h = max(2, int((meter.height() - gap * (segs - 1)) / segs))
        active = int(clamp(value, 0.0, 1.0) * segs + 0.5)

        # Pre-cache segment colors once
        c_lo   = self._c("bar_lo")
        c_mid  = self._c("bar_mid")
        c_hi   = self._c("bar_hi")
        c_off  = self._c("vu_off")
        shine  = QColor(255, 255, 255, 22)  # fixed subtle gloss, no per-seg alloc

        for i in range(segs):
            y    = meter.bottom() - (i + 1) * seg_h - i * gap
            rect = QRect(meter.left(), y, meter.width(), seg_h)
            if i < active:
                c = c_hi if i > segs * 0.86 else (c_mid if i > segs * 0.66 else c_lo)
                p.fillRect(rect, c)
                p.fillRect(QRect(rect.left() + 1, rect.top() + 1, max(1, rect.width() - 2), 1), shine)
            else:
                p.fillRect(rect, c_off)

        # Peak needle
        peak_y = meter.bottom() - int(clamp(peak, 0.0, 1.0) * max(1, meter.height()))
        p.setPen(QPen(self._c("peak"), 1))
        p.drawLine(meter.left(), peak_y, meter.right(), peak_y)


class ClickableLabel(QLabel):
    clicked = Signal()

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class LedLabel(QLabel):
    def __init__(self, text: str = "IDLE", parent: Optional[QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(110)
        self.set_state("idle")

    def set_state(self, state: str) -> None:
        state = state.lower()
        colors = {
            "playing": ("#2a0707", "#ff2d2d", "#ffffff"),
            "paused": ("#2a2104", "#ffc857", "#fff3c4"),
            "loading": ("#111111", "#ffffff", "#ffffff"),
            "stopped": ("#281010", "#ff6b6b", "#ffd6d6"),
            "idle": ("#111418", "#aab2bd", "#f5f5f5"),
        }
        bg, border, fg = colors.get(state, colors["idle"])
        self.setText(state.upper())
        self.setStyleSheet(
            f"QLabel {{ background:{bg}; color:{fg}; border:1px solid {border}; "
            "border-radius:10px; padding:6px 10px; font-weight:700; }"
        )


class SeekSlider(QSlider):
    dragging_changed = Signal(bool)
    preview_value_changed = Signal(int)
    seek_committed = Signal(int)

    def __init__(self, orientation: Qt.Orientation, parent: Optional[QWidget] = None) -> None:
        super().__init__(orientation, parent)
        self._duration_seconds = 0.0
        self._mouse_dragging = False
        self.setMinimumHeight(44)
        self.setMouseTracking(True)

    def set_duration_seconds(self, seconds: float) -> None:
        self._duration_seconds = max(0.0, float(seconds))
        self.update()

    def _value_from_pos(self, pos: QPoint) -> int:
        groove_left = 8
        groove_right = max(groove_left + 1, self.width() - 8)
        x = clamp(float(pos.x()), groove_left, groove_right)
        ratio = (x - groove_left) / float(groove_right - groove_left)
        return int(self.minimum() + ratio * (self.maximum() - self.minimum()))

    def mousePressEvent(self, event: Any) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self._mouse_dragging = True
            self.dragging_changed.emit(True)
            value = self._value_from_pos(event.position().toPoint())
            self.setValue(value)
            self.preview_value_changed.emit(value)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:  # noqa: N802
        if self._mouse_dragging:
            value = self._value_from_pos(event.position().toPoint())
            self.setValue(value)
            self.preview_value_changed.emit(value)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:  # noqa: N802
        if self._mouse_dragging and event.button() == Qt.LeftButton:
            value = self._value_from_pos(event.position().toPoint())
            self.setValue(value)
            self.preview_value_changed.emit(value)
            self.seek_committed.emit(value)
            self._mouse_dragging = False
            self.dragging_changed.emit(False)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        super().paintEvent(event)
        if self._duration_seconds <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        h = self.height()
        groove_left = 8
        groove_right = max(groove_left + 1, w - 8)
        y_major = h - 21
        p.setPen(QPen(QColor(255, 70, 70, 130), 1))
        divisions = 8 if self._duration_seconds >= 240 else 4
        for i in range(divisions + 1):
            ratio = i / divisions
            x = groove_left + int((groove_right - groove_left) * ratio)
            p.drawLine(x, y_major, x, y_major + (8 if i in (0, divisions) else 5))
            sec = self._duration_seconds * ratio
            label = format_seconds(sec)
            p.setFont(QFont("DejaVu Sans Mono", 7))
            p.setPen(QColor(255, 235, 235, 190))
            if i == 0:
                rect = QRect(0, h - 17, 70, 14)
                flags = Qt.AlignLeft | Qt.AlignVCenter
            elif i == divisions:
                rect = QRect(max(0, w - 70), h - 17, 70, 14)
                flags = Qt.AlignRight | Qt.AlignVCenter
            else:
                rect = QRect(max(0, x - 36), h - 17, 72, 14)
                flags = Qt.AlignCenter
            p.drawText(rect, flags, label)
            p.setPen(QPen(QColor(255, 70, 70, 130), 1))
        p.end()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(1660, 920)
        self.setMinimumSize(1320, 760)
        self.setAcceptDrops(True)

        # --- Core objects ---
        self.settings = SettingsStore()
        self.playlist_model = PlaylistModel(self)
        self.playlist_proxy = PlaylistProxyModel(self)
        self.playlist_proxy.setSourceModel(self.playlist_model)
        self.engine = MpvEngine(self)
        self.analyzer = RealFftAnalyzer(self)

        # --- State ---
        self._scan_jobs: List[Dict[str, Any]] = []
        self._current_source = ""
        self._seek_dragging = False
        self._last_duration = 0.0
        self._last_position = 0.0
        self._playback_state = "idle"
        self._repeat = False
        self._shuffle = False
        self._shuffle_bag: List[int] = []
        self._play_history: List[int] = []
        self._ignore_eof_until = 0.0
        self._manual_nav_inflight = False
        self._eof_guard = False
        self._eof_watchdog_armed = False
        self._audio_outputs: List[Dict[str, str]] = []
        self._suppress_auto_advance_until = 0.0
        self._transport_intent = "idle"
        self._loading_settings = True
        self._show_remaining = False
        self._is_muted = False
        self._pre_mute_volume = 80
        self._is_fullscreen = False
        self._stream_reconnect_attempts = 0
        self._stream_reconnect_max = 5

        self._build_actions()
        self._build_ui()
        self._connect_signals()
        self._load_settings()
        self._install_shortcuts()
        self._loading_settings = False

        self.health_timer = QTimer(self)
        self.health_timer.setInterval(750)
        self.health_timer.timeout.connect(self._heartbeat)
        self.health_timer.start()

        if not self.engine.available:
            self._log("ERROR: mpv backend is not available. Playback will not work until dependencies are installed.")

    def _build_actions(self) -> None:
        self.act_add_files = QAction("Add Files", self)
        self.act_add_folder = QAction("Add Folder", self)
        self.act_add_url = QAction("Add URL / Stream", self)
        self.act_clear_playlist = QAction("Clear Playlist", self)
        self.act_exit = QAction("Exit", self)
        self.act_about = QAction("About", self)
        self.act_open_config = QAction("Open Config Folder", self)

        self.act_add_files.triggered.connect(self.add_files_dialog)
        self.act_add_folder.triggered.connect(self.add_folder_dialog)
        self.act_add_url.triggered.connect(self.add_url_dialog)
        self.act_clear_playlist.triggered.connect(self.clear_playlist)
        self.act_exit.triggered.connect(self.close)
        self.act_about.triggered.connect(self.about_dialog)
        self.act_open_config.triggered.connect(self.open_config_folder)

        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.act_add_files)
        file_menu.addAction(self.act_add_folder)
        file_menu.addAction(self.act_add_url)
        file_menu.addSeparator()
        file_menu.addAction(self.act_open_config)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.act_about)

    def _build_ui(self) -> None:
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)

        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        root_layout.addWidget(self._make_header())

        self.audio_panel = self._make_audio_io_panel(root)
        root_layout.addWidget(self.audio_panel, 0)

        self.main_splitter = QSplitter(Qt.Horizontal, root)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self._make_deck_panel())
        self.playlist_panel = self._make_playlist_panel()
        self.main_splitter.addWidget(self.playlist_panel)
        self.main_splitter.setStretchFactor(0, 8)
        self.main_splitter.setStretchFactor(1, 4)
        self.main_splitter.setSizes([1060, 560])
        root_layout.addWidget(self.main_splitter, 1)

        self.log_panel = self._make_log_panel()
        root_layout.addWidget(self.log_panel, 0)

        self.setCentralWidget(root)
        self._apply_theme()

    def _make_header(self) -> QWidget:
        box = QFrame(self)
        box.setObjectName("HeaderFrame")
        layout = QHBoxLayout(box)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(10)

        title = QLabel(f"{APP_NAME} {APP_VERSION}")
        title.setObjectName("TitleLabel")
        title.setMinimumWidth(260)
        layout.addWidget(title)

        self.track_label = QLabel("Realtime MPV playback · Real PCM FFT analyzer")
        self.track_label.setObjectName("TrackLabel")
        self.track_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.track_label, 1)

        self.state_led = LedLabel("IDLE")
        layout.addWidget(self.state_led)

        self.btn_toggle_playlist = QPushButton("PL")
        self.btn_toggle_playlist.clicked.connect(self.toggle_playlist_panel)
        layout.addWidget(self.btn_toggle_playlist)

        self.btn_toggle_log = QPushButton("LOG")
        self.btn_toggle_log.clicked.connect(self.toggle_log_panel)
        layout.addWidget(self.btn_toggle_log)
        return box

    def _create_analyzer_panel(self, parent: QWidget) -> QWidget:
        # Use the Python renderer by default. The C++ Qt widget in native/ can be swapped
        # in by setting PYTUNE_USE_NATIVE_WIDGET=1 (requires a successful Shiboken build).
        use_native = os.environ.get("PYTUNE_USE_NATIVE_WIDGET", "0").lower() in ("1", "true", "yes", "on")
        if not use_native:
            self._native_widget_loaded = False
            QTimer.singleShot(0, lambda: self._log("Python high-performance spectrum renderer active; native widget optional"))
            return AnalyzerPanel(parent)
        try:
            import pytune_hfplus_native as native  # type: ignore
            widget = native.FFTSpectrumWidget(parent)
            if hasattr(widget, "setMinimumHeight"):
                widget.setMinimumHeight(300)
            self._native_widget_loaded = True
            QTimer.singleShot(0, lambda: self._log("native C++ FFTSpectrumWidget loaded"))
            return widget
        except Exception as exc:
            self._native_widget_loaded = False
            QTimer.singleShot(0, lambda: self._log(f"native widget not loaded; Python analyzer panel active: {exc}"))
            return AnalyzerPanel(parent)

    def _make_deck_panel(self) -> QWidget:
        box = QWidget(self)
        box.setMinimumWidth(720)
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        lcd = QFrame(box)
        lcd.setObjectName("LcdFrame")
        lcd_layout = QGridLayout(lcd)
        lcd_layout.setContentsMargins(14, 12, 14, 12)
        lcd_layout.setHorizontalSpacing(10)
        lcd_layout.setVerticalSpacing(8)

        self.lbl_title = QLabel("READY")
        self.lbl_title.setObjectName("LcdTitle")
        self.lbl_title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lcd_layout.addWidget(self.lbl_title, 0, 0, 1, 4)

        self.lbl_source = QLabel("Drop audio files, add a folder, or add a stream URL")
        self.lbl_source.setObjectName("LcdSub")
        self.lbl_source.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lcd_layout.addWidget(self.lbl_source, 1, 0, 1, 4)

        self.lbl_position = QLabel("0:00 / --:--")
        self.lbl_position.setObjectName("MonoLabel")
        lcd_layout.addWidget(self.lbl_position, 2, 0)

        self.lbl_meta = QLabel("metadata: --")
        self.lbl_meta.setObjectName("MonoLabel")
        self.lbl_meta.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lcd_layout.addWidget(self.lbl_meta, 2, 1, 1, 3)
        layout.addWidget(lcd, 0)

        self.analyzer_panel = self._create_analyzer_panel(box)
        layout.addWidget(self.analyzer_panel, 1)

        seek_row = QHBoxLayout()
        self.lbl_elapsed = ClickableLabel("0:00")
        self.lbl_elapsed.setObjectName("MonoLabel")
        self.lbl_elapsed.setCursor(Qt.PointingHandCursor)
        self.lbl_elapsed.setToolTip("Click to toggle remaining time")
        self.seek_slider = SeekSlider(Qt.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.setValue(0)
        self.seek_slider.setSingleStep(1000)
        self.seek_slider.setPageStep(10000)
        self.lbl_total = QLabel("--:--")
        self.lbl_total.setObjectName("MonoLabel")
        seek_row.addWidget(self.lbl_elapsed)
        seek_row.addWidget(self.seek_slider, 1)
        seek_row.addWidget(self.lbl_total)
        layout.addLayout(seek_row)

        control_frame = QFrame(box)
        control_frame.setObjectName("ControlFrame")
        controls = QHBoxLayout(control_frame)
        controls.setContentsMargins(10, 10, 10, 10)
        controls.setSpacing(8)

        self.btn_prev = QPushButton("⏮")
        self.btn_play = QPushButton("▶")
        self.btn_pause = QPushButton("⏸")
        self.btn_stop = QPushButton("■")
        self.btn_next = QPushButton("⏭")
        for btn in (self.btn_prev, self.btn_play, self.btn_pause, self.btn_stop, self.btn_next):
            btn.setMinimumHeight(42)
            btn.setMinimumWidth(58)
            controls.addWidget(btn)

        controls.addSpacing(8)
        self.btn_add_files = QPushButton("Add Files")
        self.btn_add_folder = QPushButton("Add Folder")
        self.btn_add_url = QPushButton("Add URL")
        controls.addWidget(self.btn_add_files)
        controls.addWidget(self.btn_add_folder)
        controls.addWidget(self.btn_add_url)

        controls.addSpacing(8)
        self.btn_mute = QPushButton("🔊")
        self.btn_mute.setMinimumHeight(42)
        self.btn_mute.setMinimumWidth(48)
        self.btn_mute.setToolTip("Mute / Unmute (M)")
        controls.addWidget(self.btn_mute)
        self.btn_fullscreen = QPushButton("⛶")
        self.btn_fullscreen.setMinimumHeight(42)
        self.btn_fullscreen.setMinimumWidth(48)
        self.btn_fullscreen.setToolTip("Toggle fullscreen (F11)")
        controls.addWidget(self.btn_fullscreen)

        controls.addStretch(1)
        self.chk_repeat = QCheckBox("Repeat All")
        self.chk_shuffle = QCheckBox("Shuffle")
        controls.addWidget(self.chk_repeat)
        controls.addWidget(self.chk_shuffle)
        layout.addWidget(control_frame, 0)
        return box

    def _make_audio_io_panel(self, parent: QWidget) -> QWidget:
        panel = QFrame(parent)
        panel.setObjectName("AudioIoFrame")
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(12, 8, 12, 8)
        outer.setSpacing(5)

        def ctl_label(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("ControlLabel")
            lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            return lbl

        def row_title(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setObjectName("SmallTitle")
            lbl.setMinimumWidth(82)
            return lbl

        # ── Audio I/O path ─────────────────────────────────────────────────
        row0 = QHBoxLayout()
        row0.setSpacing(6)
        row0.addWidget(row_title("AUDIO PATH"))
        row0.addWidget(ctl_label("Output"))
        self.audio_output_combo = QComboBox()
        self.audio_output_combo.setMinimumWidth(220)
        self.audio_output_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row0.addWidget(self.audio_output_combo, 3)
        self.btn_refresh_audio = QPushButton("↻")
        self.btn_refresh_audio.setFixedWidth(34)
        row0.addWidget(self.btn_refresh_audio)
        row0.addSpacing(12)
        row0.addWidget(ctl_label("Volume"))
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 130)
        self.volume_slider.setValue(80)
        self.volume_slider.setMinimumWidth(110)
        self.volume_slider.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row0.addWidget(self.volume_slider, 2)
        self.lbl_volume = QLabel("80%")
        self.lbl_volume.setObjectName("MonoLabel")
        self.lbl_volume.setMinimumWidth(44)
        row0.addWidget(self.lbl_volume)
        outer.addLayout(row0)

        # ── Analyzer controls ──────────────────────────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(6)
        row1.addWidget(row_title("ANALYZER"))
        row1.addWidget(ctl_label("FFT"))
        self.analyzer_backend_combo = QComboBox()
        for key, label_text in ANALYZER_BACKENDS:
            self.analyzer_backend_combo.addItem(label_text, key)
        self.analyzer_backend_combo.setMinimumWidth(175)
        self.analyzer_backend_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row1.addWidget(self.analyzer_backend_combo, 2)
        row1.addSpacing(6)
        row1.addWidget(ctl_label("FFT Frame Size"))
        self.fft_size_combo = QComboBox()
        for size in FFT_SIZES:
            self.fft_size_combo.addItem(str(size), size)
        self.fft_size_combo.setMinimumWidth(76)
        row1.addWidget(self.fft_size_combo)
        row1.addSpacing(6)
        row1.addWidget(ctl_label("FFT Bars"))
        self.bar_count_combo = QComboBox()
        for count in BAR_COUNTS:
            self.bar_count_combo.addItem(f"{count} bars", count)
        self.bar_count_combo.setMinimumWidth(88)
        row1.addWidget(self.bar_count_combo)
        row1.addSpacing(6)
        row1.addWidget(ctl_label("FPS"))
        self.render_fps_combo = QComboBox()
        for fps in RENDER_FPS_VALUES:
            self.render_fps_combo.addItem(f"{fps} FPS", fps)
        self.render_fps_combo.setMinimumWidth(80)
        row1.addWidget(self.render_fps_combo)
        row1.addSpacing(12)
        row1.addWidget(ctl_label("Theme"))
        self.spectrum_theme_combo = QComboBox()
        for key, theme in SPECTRUM_THEMES.items():
            self.spectrum_theme_combo.addItem(theme.get("name", key), key)
        self.spectrum_theme_combo.setMinimumWidth(180)
        self.spectrum_theme_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row1.addWidget(self.spectrum_theme_combo, 2)
        row1.addSpacing(6)
        row1.addWidget(ctl_label("Visual"))
        self.spectrum_visual_combo = QComboBox()
        for key, label_text in SPECTRUM_VISUAL_MODES:
            self.spectrum_visual_combo.addItem(label_text, key)
        self.spectrum_visual_combo.setMinimumWidth(165)
        self.spectrum_visual_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        row1.addWidget(self.spectrum_visual_combo, 2)
        row1.addSpacing(6)
        row1.addWidget(ctl_label("Smooth"))
        self.smooth_combo = QComboBox()
        for key, lbl_text in (("fast", "Fast"), ("medium", "Medium"), ("slow", "Slow")):
            self.smooth_combo.addItem(lbl_text, key)
        self.smooth_combo.setCurrentIndex(1)
        self.smooth_combo.setMinimumWidth(74)
        row1.addWidget(self.smooth_combo)
        row1.addSpacing(6)
        row1.addWidget(ctl_label("Peaks"))
        self.peak_decay_combo = QComboBox()
        for key, lbl_text in (("fast", "Fast"), ("medium", "Medium"), ("hold", "Hold"), ("freeze", "Freeze")):
            self.peak_decay_combo.addItem(lbl_text, key)
        self.peak_decay_combo.setCurrentIndex(1)
        self.peak_decay_combo.setMinimumWidth(80)
        row1.addWidget(self.peak_decay_combo)
        row1.addSpacing(4)
        self.btn_reset_peaks = QPushButton("↯ Peaks")
        self.btn_reset_peaks.setToolTip("Reset all peak hold caps")
        self.btn_reset_peaks.setMinimumHeight(26)
        row1.addWidget(self.btn_reset_peaks)
        outer.addLayout(row1)
        return panel


    def _make_playlist_panel(self) -> QWidget:
        group = QGroupBox("Integrated Playlist", self)
        group.setMinimumWidth(440)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        tool_row = QHBoxLayout()
        self.btn_pl_up = QPushButton("↑")
        self.btn_pl_down = QPushButton("↓")
        self.btn_pl_remove = QPushButton("Remove")
        self.btn_pl_clear = QPushButton("Clear")
        self.btn_pl_save = QPushButton("Save PL")
        self.btn_pl_load = QPushButton("Load PL")
        self.playlist_filter = QLineEdit()
        self.playlist_filter.setPlaceholderText("Filter title/source/type")
        tool_row.addWidget(self.btn_pl_up)
        tool_row.addWidget(self.btn_pl_down)
        tool_row.addWidget(self.btn_pl_remove)
        tool_row.addWidget(self.btn_pl_clear)
        tool_row.addWidget(self.btn_pl_save)
        tool_row.addWidget(self.btn_pl_load)
        tool_row.addWidget(self.playlist_filter, 1)
        layout.addLayout(tool_row)

        self.playlist_view = QTableView(group)
        self.playlist_view.setModel(self.playlist_proxy)
        self.playlist_view.setSelectionBehavior(QTableView.SelectRows)
        self.playlist_view.setSelectionMode(QTableView.ExtendedSelection)
        self.playlist_view.setAlternatingRowColors(True)
        self.playlist_view.setSortingEnabled(True)
        self.playlist_view.verticalHeader().setVisible(False)
        self.playlist_view.horizontalHeader().setStretchLastSection(False)
        self.playlist_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.playlist_view.setColumnWidth(0, 46)
        self.playlist_view.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.playlist_view.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.playlist_view.setColumnWidth(2, 92)
        self.playlist_view.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.playlist_view.setColumnWidth(3, 78)
        self.playlist_view.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        layout.addWidget(self.playlist_view, 1)

        self.scan_progress = QProgressBar(group)
        self.scan_progress.setRange(0, 0)
        self.scan_progress.setVisible(False)
        layout.addWidget(self.scan_progress)
        return group

    def _make_log_panel(self) -> QWidget:
        group = QGroupBox("Debug / Backend Log", self)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 10, 10, 10)
        self.log_text = QPlainTextEdit(group)
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumBlockCount(1600)
        self.log_text.setMinimumHeight(110)
        layout.addWidget(self.log_text)
        return group

    def _connect_signals(self) -> None:
        # Transport
        self.btn_play.clicked.connect(self.play_selected_or_resume)
        self.btn_pause.clicked.connect(self.engine.toggle_pause)
        self.btn_stop.clicked.connect(self.stop_playback)
        self.btn_prev.clicked.connect(self.play_previous)
        self.btn_next.clicked.connect(self.play_next)
        self.btn_mute.clicked.connect(self.toggle_mute)
        self.btn_fullscreen.clicked.connect(self.toggle_fullscreen)
        self.lbl_elapsed.clicked.connect(self.toggle_remaining_display)

        # Playlist controls
        self.btn_add_files.clicked.connect(self.add_files_dialog)
        self.btn_add_folder.clicked.connect(self.add_folder_dialog)
        self.btn_add_url.clicked.connect(self.add_url_dialog)
        self.btn_pl_remove.clicked.connect(self.remove_selected_tracks)
        self.btn_pl_clear.clicked.connect(self.clear_playlist)
        self.btn_pl_up.clicked.connect(self.move_selected_up)
        self.btn_pl_down.clicked.connect(self.move_selected_down)
        self.btn_pl_save.clicked.connect(self.save_playlist_dialog)
        self.btn_pl_load.clicked.connect(self.load_playlist_dialog)
        self.chk_repeat.toggled.connect(self._set_repeat)
        self.chk_shuffle.toggled.connect(self._set_shuffle)
        self.playlist_filter.textChanged.connect(self._filter_playlist)
        self.playlist_view.doubleClicked.connect(self._playlist_double_clicked)

        # Seek / volume
        self.seek_slider.dragging_changed.connect(self._seek_dragging_changed)
        self.seek_slider.preview_value_changed.connect(self._seek_preview_changed)
        self.seek_slider.seek_committed.connect(self._seek_committed)
        self.volume_slider.valueChanged.connect(self._volume_changed)

        # Audio output
        self.audio_output_combo.currentIndexChanged.connect(self._audio_output_selected)
        self.btn_refresh_audio.clicked.connect(self.engine.refresh_audio_outputs)

        # Analyzer settings
        self.analyzer_backend_combo.currentIndexChanged.connect(self._analyzer_backend_selected)
        self.fft_size_combo.currentIndexChanged.connect(self._fft_size_selected)
        self.bar_count_combo.currentIndexChanged.connect(self._bar_count_selected)
        self.render_fps_combo.currentIndexChanged.connect(self._render_fps_changed)
        self.spectrum_theme_combo.currentIndexChanged.connect(self._spectrum_theme_selected)
        self.spectrum_visual_combo.currentIndexChanged.connect(self._spectrum_visual_selected)
        self.smooth_combo.currentIndexChanged.connect(self._smooth_speed_changed)
        self.peak_decay_combo.currentIndexChanged.connect(self._peak_decay_changed)
        self.btn_reset_peaks.clicked.connect(self._reset_peaks)

        # Engine → UI
        self.engine.log_line.connect(self._log)
        self.engine.error.connect(self._error)
        self.engine.state_changed.connect(self._state_changed)
        self.engine.position_changed.connect(self._position_changed)
        self.engine.metadata_changed.connect(self._metadata_changed)
        self.engine.eof_reached.connect(self._handle_eof)
        self.engine.source_changed.connect(self._source_changed)
        self.engine.duration_changed.connect(self._duration_changed)
        self.engine.audio_outputs_changed.connect(self._audio_outputs_changed)

        # Analyzer → panel
        self.analyzer.frame_ready.connect(self.analyzer_panel.set_frame)
        self.analyzer.log_line.connect(self._log)
        self.analyzer.error.connect(self._error)
        self.analyzer.status_changed.connect(self.analyzer_panel.set_analyzer_status)

    def _install_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.add_files_dialog)
        QShortcut(QKeySequence("Ctrl+U"), self, activated=self.add_url_dialog)
        QShortcut(QKeySequence("Ctrl+Shift+O"), self, activated=self.add_folder_dialog)
        QShortcut(QKeySequence("Space"), self, activated=self.play_selected_or_resume)
        QShortcut(QKeySequence("Ctrl+Right"), self, activated=lambda: self.engine.seek_relative(10))
        QShortcut(QKeySequence("Ctrl+Left"), self, activated=lambda: self.engine.seek_relative(-10))
        QShortcut(QKeySequence("N"), self, activated=self.play_next)
        QShortcut(QKeySequence("P"), self, activated=self.play_previous)
        QShortcut(QKeySequence("Delete"), self, activated=self.remove_selected_tracks)
        QShortcut(QKeySequence("M"), self, activated=self.toggle_mute)
        QShortcut(QKeySequence("+"), self, activated=lambda: self._adjust_volume(5))
        QShortcut(QKeySequence("-"), self, activated=lambda: self._adjust_volume(-5))
        QShortcut(QKeySequence("F"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("R"), self, activated=self._toggle_repeat_shortcut)
        QShortcut(QKeySequence("S"), self, activated=self._toggle_shuffle_shortcut)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #202329;
                color: #f4f6fa;
                font-family: DejaVu Sans, Arial, sans-serif;
                font-size: 10pt;
            }
            QToolTip {
                background: transparent;
                color: transparent;
                border: none;
            }
            QMenuBar, QMenu {
                background: #181b20;
                color: #ffffff;
                border: 1px solid #2a2a2a;
            }
            QMenuBar::item:selected, QMenu::item:selected {
                background: #ff2d2d;
                color: #ffffff;
            }
            #HeaderFrame, #ControlFrame, #AudioIoFrame, QGroupBox, #LcdFrame {
                background: #262a31;
                border: 1px solid #555e6a;
                border-radius: 10px;
            }
            QGroupBox {
                margin-top: 18px;
                padding-top: 14px;
                font-weight: 700;
                color: #ffffff;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 14px;
                padding: 0 6px;
                color: #ffffff;
                background: transparent;
            }
            QLabel {
                background: transparent;
                border: none;
            }
            #TitleLabel {
                color: #ffffff;
                font-size: 13pt;
                font-weight: 900;
            }
            #SmallTitle {
                color: #ffffff;
                font-weight: 900;
                font-family: DejaVu Sans Mono, monospace;
            }
            #TrackLabel {
                color: #e8eaee;
                font-family: DejaVu Sans Mono, monospace;
            }
            #ControlLabel {
                color: #cbd3dd;
                background: transparent;
                border: none;
                font-family: DejaVu Sans Mono, monospace;
                font-size: 9pt;
                font-weight: 800;
            }
            #LcdTitle {
                color: #ffffff;
                font-size: 15pt;
                font-weight: 900;
                font-family: DejaVu Sans Mono, monospace;
            }
            #LcdSub {
                color: #d2d7df;
                font-family: DejaVu Sans Mono, monospace;
            }
            #MonoLabel {
                color: #ffffff;
                font-family: DejaVu Sans Mono, monospace;
            }
            QPushButton {
                background: #1a1d22;
                border: 1px solid #666f7c;
                border-radius: 8px;
                color: #ffffff;
                padding: 7px 10px;
                font-weight: 800;
            }
            QPushButton:hover {
                background: #343a43;
                border-color: #ff4a4a;
                color: #ffffff;
            }
            QPushButton:pressed {
                background: #ff3a3a;
                border-color: #ffffff;
                color: #ffffff;
            }
            QPushButton:disabled {
                background: #20242a;
                color: #777777;
                border-color: #333333;
            }
            QSlider::groove:horizontal {
                height: 9px;
                background: #20242a;
                border: 1px solid #4a5058;
                border-radius: 4px;
            }
            QSlider::sub-page:horizontal {
                background: #ff2d2d;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                width: 16px;
                margin: -5px 0;
                border: 1px solid #ff2d2d;
                border-radius: 8px;
            }
            QComboBox, QSpinBox {
                background: #111419;
                color: #ffffff;
                border: 1px solid #666f7c;
                border-radius: 7px;
                padding: 6px;
                selection-background-color: #ff2d2d;
                selection-color: #ffffff;
            }
            QComboBox:hover, QSpinBox:hover {
                background: #303640;
                color: #ffffff;
                border-color: #ff4040;
            }
            QComboBox QAbstractItemView {
                background: #161a20;
                color: #f4f4f6;
                border: 1px solid #ff2d2d;
                selection-background-color: #ff2d2d;
                selection-color: #ffffff;
                outline: 0;
            }
            QCheckBox {
                color: #ffffff;
                spacing: 6px;
                font-weight: 800;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #565f6b;
                background: #111419;
                border-radius: 4px;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #ffffff;
                background: #ff2d2d;
                border-radius: 4px;
            }
            QTableView {
                background: #111419;
                alternate-background-color: #1b1f25;
                gridline-color: #303640;
                selection-background-color: #ff2d2d;
                selection-color: #ffffff;
                border: 1px solid #4a5058;
                border-radius: 8px;
            }
            QHeaderView::section {
                background: #20242a;
                color: #ffffff;
                padding: 6px;
                border: 1px solid #4a5058;
                font-weight: 800;
            }
            QLineEdit, QPlainTextEdit {
                background: #111419;
                color: #ffffff;
                border: 1px solid #4a5058;
                border-radius: 7px;
                padding: 6px;
                font-family: DejaVu Sans Mono, monospace;
                selection-background-color: #ff2d2d;
                selection-color: #ffffff;
            }
            QLineEdit:hover, QPlainTextEdit:hover {
                border-color: #ff2d2d;
            }
            QProgressBar {
                border: 1px solid #4a5058;
                border-radius: 6px;
                text-align: center;
                background: #111419;
                color: #ffffff;
            }
            QProgressBar::chunk {
                background: #ff2d2d;
            }
            QSplitter::handle {
                background: #111419;
                border: 1px solid #39424d;
                width: 6px;
            }
            QSplitter::handle:hover {
                background: #ff2d2d;
            }
            QStatusBar {
                background: #181b20;
                color: #e8eaee;
            }
            """
        )

    def _load_settings(self) -> None:
        self.playlist_model.load_jsonable(self.settings.get("playlist", []))
        volume = max(0, min(130, int(self.settings.get("volume", 80))))
        self.volume_slider.setValue(volume)
        self.engine.set_volume(volume)
        self._repeat = bool(self.settings.get("repeat", False))
        self._shuffle = bool(self.settings.get("shuffle", False))
        self.chk_repeat.setChecked(self._repeat)
        self.chk_shuffle.setChecked(self._shuffle)
        backend = str(self.settings.get("analyzer_backend", "auto"))
        idx = self.analyzer_backend_combo.findData(backend)
        self.analyzer_backend_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.analyzer.set_backend(str(self.analyzer_backend_combo.currentData() or "auto"))
        fft_size = int(self.settings.get("fft_size", 2048))
        idx = self.fft_size_combo.findData(fft_size)
        self.fft_size_combo.setCurrentIndex(idx if idx >= 0 else self.fft_size_combo.findData(2048))
        self.analyzer.set_fft_size(int(self.fft_size_combo.currentData() or 2048))
        bar_count = int(self.settings.get("bar_count", 64))
        idx = self.bar_count_combo.findData(bar_count)
        self.bar_count_combo.setCurrentIndex(idx if idx >= 0 else self.bar_count_combo.findData(64))
        self.analyzer.set_bar_count(int(self.bar_count_combo.currentData() or 64))
        if hasattr(self.analyzer_panel, "set_bar_count"):
            try:
                self.analyzer_panel.set_bar_count(int(self.bar_count_combo.currentData() or 64))
            except Exception:
                pass
        fps = int(self.settings.get("render_fps", DEFAULT_RENDER_FPS) or DEFAULT_RENDER_FPS)
        if fps not in RENDER_FPS_VALUES:
            fps = DEFAULT_RENDER_FPS
        idx = self.render_fps_combo.findData(fps)
        self.render_fps_combo.setCurrentIndex(idx if idx >= 0 else self.render_fps_combo.findData(DEFAULT_RENDER_FPS))
        self.analyzer.set_target_fps(fps)
        if hasattr(self.analyzer_panel, "set_render_fps"):
            try:
                self.analyzer_panel.set_render_fps(fps)
            except Exception:
                pass
        theme_raw = str(self.settings.get("spectrum_theme", DEFAULT_SPECTRUM_THEME))
        theme = SPECTRUM_THEME_ALIASES.get(theme_raw, theme_raw)
        idx = self.spectrum_theme_combo.findData(theme)
        self.spectrum_theme_combo.setCurrentIndex(idx if idx >= 0 else self.spectrum_theme_combo.findData(DEFAULT_SPECTRUM_THEME))
        if hasattr(self.analyzer_panel, "set_theme"):
            try:
                self.analyzer_panel.set_theme(str(self.spectrum_theme_combo.currentData() or DEFAULT_SPECTRUM_THEME))
            except Exception:
                pass
        self.log_panel.setVisible(bool(self.settings.get("log_visible", True)))
        self.playlist_panel.setVisible(bool(self.settings.get("playlist_visible", True)))
        if self.playlist_panel.isVisible():
            sizes = self.settings.get("splitter_sizes", [1060, 560])
            if not isinstance(sizes, list) or len(sizes) != 2 or sum(int(x) for x in sizes if isinstance(x, int)) < 900:
                sizes = [1060, 560]
            self.main_splitter.setSizes(sizes)
        visual = SPECTRUM_VISUAL_ALIASES.get(str(self.settings.get("spectrum_visual_mode", DEFAULT_SPECTRUM_VISUAL_MODE)), str(self.settings.get("spectrum_visual_mode", DEFAULT_SPECTRUM_VISUAL_MODE)))
        valid_visuals = {key for key, _label in SPECTRUM_VISUAL_MODES}
        if visual not in valid_visuals:
            visual = DEFAULT_SPECTRUM_VISUAL_MODE
        idx = self.spectrum_visual_combo.findData(visual)
        self.spectrum_visual_combo.setCurrentIndex(idx if idx >= 0 else self.spectrum_visual_combo.findData(DEFAULT_SPECTRUM_VISUAL_MODE))
        if hasattr(self.analyzer_panel, "set_visual_mode"):
            try:
                self.analyzer_panel.set_visual_mode(str(self.spectrum_visual_combo.currentData() or DEFAULT_SPECTRUM_VISUAL_MODE))
            except Exception:
                pass
        smooth = str(self.settings.get("smooth_speed", "medium"))
        idx = self.smooth_combo.findData(smooth)
        self.smooth_combo.setCurrentIndex(idx if idx >= 0 else 1)
        if hasattr(self.analyzer_panel, "set_smooth_speed"):
            self.analyzer_panel.set_smooth_speed(str(self.smooth_combo.currentData() or "medium"))
        peak_preset = str(self.settings.get("peak_decay", "medium"))
        idx = self.peak_decay_combo.findData(peak_preset)
        self.peak_decay_combo.setCurrentIndex(idx if idx >= 0 else 1)
        if hasattr(self.analyzer_panel, "set_peak_decay"):
            self.analyzer_panel.set_peak_decay(str(self.peak_decay_combo.currentData() or "medium"))
        self._rebuild_shuffle_bag(exclude_current=True)

    def _save_settings(self) -> None:
        self.settings.set("playlist", self.playlist_model.to_jsonable())
        self.settings.set("volume", self.volume_slider.value())
        self.settings.set("repeat", self._repeat)
        self.settings.set("shuffle", self._shuffle)
        self.settings.set("log_visible", self.log_panel.isVisible())
        self.settings.set("playlist_visible", self.playlist_panel.isVisible())
        self.settings.set("splitter_sizes", self.main_splitter.sizes())
        self.settings.set("audio_output", self.audio_output_combo.currentData() or "auto")
        self.settings.set("analyzer_backend", self.analyzer_backend_combo.currentData() or "auto")
        self.settings.set("fft_size", int(self.fft_size_combo.currentData() or 2048))
        self.settings.set("bar_count", int(self.bar_count_combo.currentData() or 64))
        self.settings.set("render_fps", int(self.render_fps_combo.currentData() if hasattr(self, "render_fps_combo") else DEFAULT_RENDER_FPS))
        self.settings.set("spectrum_theme", self.spectrum_theme_combo.currentData() or DEFAULT_SPECTRUM_THEME)
        self.settings.set("spectrum_visual_mode", self.spectrum_visual_combo.currentData() or DEFAULT_SPECTRUM_VISUAL_MODE)
        self.settings.set("smooth_speed", str(self.smooth_combo.currentData() or "medium"))
        self.settings.set("peak_decay", str(self.peak_decay_combo.currentData() or "medium"))
        self.settings.save()

    def _selected_source_rows(self) -> List[int]:
        rows: List[int] = []
        for idx in self.playlist_view.selectionModel().selectedRows():
            src_idx = self.playlist_proxy.mapToSource(idx)
            if src_idx.isValid():
                rows.append(src_idx.row())
        return rows

    @Slot(str)
    def _filter_playlist(self, text: str) -> None:
        self.playlist_proxy.setFilterFixedString(text)

    @Slot()
    def add_files_dialog(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Add audio files",
            str(Path.home()),
            "Audio Files (*.mp3 *.flac *.wav *.ogg *.opus *.m4a *.aac *.wma *.aiff *.ape);;All Files (*)",
        )
        if files:
            self._add_sources(files)

    @Slot()
    def add_folder_dialog(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Add folder recursively", str(Path.home()))
        if folder:
            self.start_folder_scan([folder])

    @Slot()
    def add_url_dialog(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Open Stream URL")
        dlg.setMinimumWidth(680)
        dlg.setModal(True)
        dlg.setStyleSheet(
            "QDialog { background:#1a1d22; border:1px solid #3a4050; border-radius:10px; }"
            "QLabel { color:#c8cdd6; font-size:10pt; }"
            "QLineEdit { background:#111418; color:#f4f6fa; border:1px solid #444c5a;"
            "  border-radius:6px; padding:8px 10px; font-size:11pt; font-family:monospace; }"
            "QLineEdit:focus { border-color:#ff2d2d; }"
            "QPushButton { background:#2a2f3a; color:#f4f6fa; border:1px solid #555e6a;"
            "  border-radius:6px; padding:8px 22px; font-size:10pt; font-weight:600; min-width:90px; }"
            "QPushButton:hover { background:#3a3f4d; border-color:#ff2d2d; color:#ffffff; }"
            "QPushButton:pressed { background:#ff2d2d; color:#ffffff; border-color:#ff2d2d; }"
            "#btn_open { background:#c0242e; border-color:#e0353f; color:#ffffff; }"
            "#btn_open:hover { background:#e02530; border-color:#ff4a55; }"
        )
        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 20, 20, 20)
        v.setSpacing(14)
        lbl = QLabel("Enter a stream URL, HTTP audio link, or playlist file (PLS / M3U / M3U8):")
        lbl.setWordWrap(True)
        v.addWidget(lbl)
        url_edit = QLineEdit()
        url_edit.setPlaceholderText("https://  or  http://  or  /path/to/stream.pls")
        url_edit.setMinimumHeight(40)
        url_edit.setClearButtonEnabled(True)
        v.addWidget(url_edit)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_cancel = QPushButton("Dismiss")
        btn_open = QPushButton("Open Stream")
        btn_open.setObjectName("btn_open")
        btn_row.addWidget(btn_cancel)
        btn_row.addSpacing(8)
        btn_row.addWidget(btn_open)
        v.addLayout(btn_row)
        btn_cancel.clicked.connect(dlg.reject)
        btn_open.clicked.connect(dlg.accept)
        url_edit.returnPressed.connect(dlg.accept)
        btn_open.setDefault(True)
        url_edit.setFocus()
        if dlg.exec() == QDialog.Accepted and url_edit.text().strip():
            self._add_sources([url_edit.text().strip()])

    def _add_sources(self, sources: Iterable[str]) -> None:
        # Build all Track objects before touching the model, then insert in one go.
        # Disabling sort during insert prevents the table from re-sorting on every row,
        # which was the main lag with large folders.
        src_list = list(sources)
        tracks: List[Track] = []
        skipped_non_audio = 0
        for n, source in enumerate(src_list, 1):
            norm = normalize_source(source)
            if not norm:
                continue
            if is_stream_source(norm):
                tracks.append(Track.from_source(norm))
            else:
                path = Path(norm)
                if path.is_file() and is_audio_file(path):
                    tracks.append(Track.from_source(norm))
                else:
                    skipped_non_audio += 1
            if n % 500 == 0:
                QApplication.processEvents(QEventLoop.ExcludeUserInputEvents, 3)
        was_sorting = False
        try:
            was_sorting = self.playlist_view.isSortingEnabled()
            if was_sorting:
                self.playlist_view.setSortingEnabled(False)
        except Exception:
            pass
        try:
            added, skipped = self.playlist_model.add_tracks(tracks)
        finally:
            try:
                self.playlist_view.setSortingEnabled(was_sorting)
            except Exception:
                pass
        self._log(f"playlist add: {added} added, {skipped} duplicates, {skipped_non_audio} non-audio skipped")
        self._rebuild_shuffle_bag(exclude_current=True)

    def start_folder_scan(self, folders: List[str]) -> None:
        thread = QThread(self)
        worker = FileScanWorker(folders, recursive=True)
        worker.moveToThread(thread)
        job = {"thread": thread, "worker": worker}
        self._scan_jobs.append(job)
        self.scan_progress.setVisible(True)
        thread.started.connect(worker.run)
        worker.found.connect(lambda batch: self._add_sources(batch))
        worker.progress.connect(lambda path, count: self._log(f"scan: {count} audio files found"))
        worker.error.connect(self._error)
        worker.finished.connect(lambda: self._finish_scan_job(job))
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()
        self._log(f"folder scan started: {folders}")

    def _finish_scan_job(self, job: Dict[str, Any]) -> None:
        try:
            self._scan_jobs.remove(job)
        except ValueError:
            pass
        self.scan_progress.setVisible(bool(self._scan_jobs))
        self._log("folder scan finished")

    @Slot()
    def remove_selected_tracks(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            return
        current = self.playlist_model.current_row
        removed_current = current in rows
        removed = self.playlist_model.remove_rows(rows)
        self._log(f"playlist remove: {removed} row(s)")
        if removed_current:
            self.stop_playback()
        self._rebuild_shuffle_bag(exclude_current=True)

    @Slot()
    def clear_playlist(self) -> None:
        self.stop_playback()
        self.playlist_model.clear()
        self._shuffle_bag.clear()
        self._play_history.clear()
        self._log("playlist cleared")

    @Slot()
    def save_playlist_dialog(self) -> None:
        tracks = self.playlist_model.tracks()
        if not tracks:
            dlg = QDialog(self)
            dlg.setWindowTitle("Save Playlist")
            dlg.setModal(True)
            dlg.setMinimumWidth(340)
            dlg.setStyleSheet(
                "QDialog{background:#1a1d22;border:1px solid #3a4050;border-radius:8px;}"
                "QLabel{color:#c8cdd8;font-size:13px;}"
                "#btn_close{background:#3a4050;color:#c8cdd8;border:none;border-radius:5px;"
                "padding:6px 18px;font-size:13px;}"
                "#btn_close:hover{background:#4a5060;}"
            )
            v = QVBoxLayout(dlg)
            v.setContentsMargins(20, 20, 20, 16)
            v.setSpacing(12)
            v.addWidget(QLabel("Playlist is empty — nothing to save."))
            btn = QPushButton("Close")
            btn.setObjectName("btn_close")
            btn.clicked.connect(dlg.reject)
            h = QHBoxLayout()
            h.addStretch()
            h.addWidget(btn)
            v.addLayout(h)
            dlg.exec()
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Playlist",
            str(Path.home() / "playlist.json"),
            "Pytune Playlist (*.json);;All Files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"

        payload = {
            "pytune_playlist_version": 1,
            "created": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
            "tracks": [
                {
                    "source": t.source,
                    "title": t.title,
                    "kind": t.kind,
                    "duration": t.duration,
                }
                for t in tracks
            ],
        }
        try:
            Path(path).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
            self._log(f"playlist saved: {path} ({len(tracks)} tracks)")
        except Exception as exc:
            self._log(f"playlist save error: {exc}")
            err_dlg = QDialog(self)
            err_dlg.setWindowTitle("Save Failed")
            err_dlg.setModal(True)
            err_dlg.setMinimumWidth(380)
            err_dlg.setStyleSheet(
                "QDialog{background:#1a1d22;border:1px solid #3a4050;border-radius:8px;}"
                "QLabel{color:#ff6060;font-size:13px;}"
                "#btn_ok{background:#3a4050;color:#c8cdd8;border:none;border-radius:5px;padding:6px 18px;font-size:13px;}"
                "#btn_ok:hover{background:#4a5060;}"
            )
            ev = QVBoxLayout(err_dlg)
            ev.setContentsMargins(20, 20, 20, 16)
            ev.setSpacing(10)
            ev.addWidget(QLabel(f"Could not write playlist file:\n{exc}"))
            bok = QPushButton("OK")
            bok.setObjectName("btn_ok")
            bok.clicked.connect(err_dlg.accept)
            bh = QHBoxLayout()
            bh.addStretch()
            bh.addWidget(bok)
            ev.addLayout(bh)
            err_dlg.exec()

    @Slot()
    def load_playlist_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Playlist",
            str(Path.home()),
            "Pytune Playlist (*.json);;All Files (*)",
        )
        if not path:
            return

        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            self._log(f"playlist load error (parse): {exc}")
            return

        if not isinstance(raw, dict) or "tracks" not in raw:
            self._log("playlist load error: not a valid Pytune playlist file")
            return

        raw_tracks = raw.get("tracks", [])
        if not isinstance(raw_tracks, list):
            self._log("playlist load error: 'tracks' key is not a list")
            return

        tracks: List[Track] = []
        for item in raw_tracks:
            if not isinstance(item, dict):
                continue
            source = str(item.get("source", "")).strip()
            if not source:
                continue
            norm = normalize_source(source)
            if not norm:
                continue
            kind = str(item.get("kind", "file"))
            if kind not in ("file", "stream"):
                kind = "stream" if is_stream_source(norm) else "file"
            duration = item.get("duration")
            try:
                duration = float(duration) if duration is not None else None
            except (TypeError, ValueError):
                duration = None
            title = str(item.get("title", "")).strip() or title_from_source(norm)
            tracks.append(Track(
                uid=str(uuid.uuid4()),
                source=norm,
                title=title,
                kind=kind,
                duration=duration,
            ))

        if not tracks:
            self._log("playlist load: file contained no valid tracks")
            return

        added, skipped = self.playlist_model.add_tracks(tracks)
        self._rebuild_shuffle_bag(exclude_current=True)
        self._log(
            f"playlist loaded: {path} — {added} added, {skipped} duplicates skipped"
            f" (v{raw.get('pytune_playlist_version', '?')})"
        )

    @Slot()
    def move_selected_up(self) -> None:
        self.playlist_model.move_up(self._selected_source_rows())
        self._rebuild_shuffle_bag(exclude_current=True)

    @Slot()
    def move_selected_down(self) -> None:
        self.playlist_model.move_down(self._selected_source_rows())
        self._rebuild_shuffle_bag(exclude_current=True)

    @Slot(QModelIndex)
    def _playlist_double_clicked(self, index: QModelIndex) -> None:
        src_idx = self.playlist_proxy.mapToSource(index)
        if src_idx.isValid():
            self.play_track(src_idx.row())

    def _rebuild_shuffle_bag(self, exclude_current: bool = True) -> None:
        import random

        count = self.playlist_model.rowCount()
        rows = list(range(count))
        current = self.playlist_model.current_row
        if exclude_current and count > 1 and current in rows:
            rows.remove(current)
        random.shuffle(rows)
        self._shuffle_bag = rows

    def _mark_row_consumed_from_shuffle_bag(self, row: int) -> None:
        self._shuffle_bag = [x for x in self._shuffle_bag if x != row]

    def _push_history(self, row: int) -> None:
        if row < 0:
            return
        if self._play_history and self._play_history[-1] == row:
            return
        self._play_history.append(row)
        if len(self._play_history) > 256:
            self._play_history = self._play_history[-256:]

    def _resolve_current_row(self, set_model: bool = False) -> int:
        count = self.playlist_model.rowCount()
        current = self.playlist_model.current_row
        if 0 <= current < count:
            return current
        if self._current_source:
            for row, track in enumerate(self.playlist_model.tracks()):
                if track.source == self._current_source:
                    if set_model:
                        self.playlist_model.set_current_row(row)
                    return row
        rows = self._selected_source_rows() if hasattr(self, "playlist_view") else []
        if rows:
            row = rows[0]
            if 0 <= row < count:
                if set_model:
                    self.playlist_model.set_current_row(row)
                return row
        return -1

    def _select_playlist_row(self, row: int) -> None:
        try:
            src_idx = self.playlist_model.index(row, 0)
            proxy_idx = self.playlist_proxy.mapFromSource(src_idx)
            if proxy_idx.isValid():
                self.playlist_view.selectRow(proxy_idx.row())
                self.playlist_view.scrollTo(proxy_idx)
        except Exception:
            pass

    def _next_row(self, from_eof: bool = False) -> int:
        count = self.playlist_model.rowCount()
        if count <= 0:
            return -1
        current = self._resolve_current_row(set_model=True)
        if current < 0:
            return 0

        manual_nav = not bool(from_eof)
        if self._shuffle:
            self._push_history(current)
            self._mark_row_consumed_from_shuffle_bag(current)
            if not self._shuffle_bag:
                # Manual NEXT must always wrap through the playlist. EOF only wraps when Repeat is enabled.
                if from_eof and not self._repeat:
                    return -1
                self._rebuild_shuffle_bag(exclude_current=count > 1)
            if self._shuffle_bag:
                return self._shuffle_bag.pop(0)
            return current if count == 1 and (manual_nav or self._repeat) else -1

        next_row = current + 1
        if next_row < count:
            self._push_history(current)
            return next_row
        if manual_nav or self._repeat:
            self._push_history(current)
            return 0
        return -1

    def _previous_row(self, manual_nav: bool = True) -> int:
        count = self.playlist_model.rowCount()
        if count <= 0:
            return -1
        current = self._resolve_current_row(set_model=True)
        if current < 0:
            return 0
        if self._shuffle and self._play_history:
            while self._play_history:
                row = self._play_history.pop()
                if 0 <= row < count and row != current:
                    # Make current available again for future shuffle traversal.
                    if current >= 0 and current not in self._shuffle_bag:
                        self._shuffle_bag.insert(0, current)
                    return row
        prev_row = current - 1
        if prev_row < 0:
            return count - 1 if (manual_nav or self._repeat) else -1
        return prev_row

    @Slot()
    def play_selected_or_resume(self) -> None:
        rows = self._selected_source_rows()
        current = self.playlist_model.current_row
        if rows and rows[0] != current:
            self.play_track(rows[0], reason="direct")
            return
        if current >= 0:
            if self._playback_state == "paused":
                self._transport_intent = "resume"
                self._eof_guard = False
                self._ignore_eof_until = time.perf_counter() + 0.25
                self.engine.play()
                self.analyzer.set_playback_state("playing")
            elif self._playback_state in ("stopped", "idle"):
                self.play_track(current, reason="direct")
            elif self._playback_state == "playing":
                self._log("PLAY: already playing")
            else:
                self.play_track(current, reason="direct")
            return
        if self.playlist_model.rowCount() > 0:
            self.play_track(0, reason="direct")

    def play_track(self, row: int, reason: str = "direct") -> None:
        track = self.playlist_model.track_at(row)
        if track is None:
            return
        previous_row = self.playlist_model.current_row
        if reason in ("next", "previous", "eof") and previous_row >= 0 and previous_row != row:
            self._push_history(previous_row)
        if reason != "stream-reconnect":
            self._stream_reconnect_attempts = 0
        self._transport_intent = reason
        self._eof_guard = False
        self._eof_watchdog_armed = False
        self._suppress_auto_advance_until = 0.0
        self._ignore_eof_until = time.perf_counter() + 0.85
        self.playlist_model.set_current_row(row)
        self._select_playlist_row(row)
        self.lbl_title.setText(track.title)
        self.lbl_source.setText(track.source)
        self.track_label.setText("PLAYING · REAL FFT ACTIVE")
        self._current_source = track.source
        self._last_position = 0.0
        self._last_duration = 0.0
        self.seek_slider.setValue(0)
        self._playback_state = "loading"
        self.analyzer_panel.set_state("loading")
        self.engine.load(track.source)
        QTimer.singleShot(120, lambda src=track.source: self._start_analyzer_if_current(src, 0.0))
        self._mark_row_consumed_from_shuffle_bag(row)
        if reason == "direct" and self._shuffle:
            self._play_history.clear()
            self._rebuild_shuffle_bag(exclude_current=True)
        self._log(f"playing row {row + 1} [{reason}]: {track.title}")

    def _start_analyzer_if_current(self, source: str, start_pos: float) -> None:
        if source != self._current_source:
            self._log("analyzer start skipped: source changed before startup")
            return
        if self._transport_intent == "stop":
            self._log("analyzer start skipped: transport is stopped")
            return
        self.analyzer.start(source, start_pos)
        self.analyzer.set_playback_state("playing" if self._playback_state in ("playing", "loading") else self._playback_state)

    @Slot()
    def play_next(self) -> None:
        self._manual_nav_inflight = True
        self._transport_intent = "next"
        self._ignore_eof_until = time.perf_counter() + 0.95
        self._suppress_auto_advance_until = time.perf_counter() + 0.95
        self._resolve_current_row(set_model=True)
        next_row = self._next_row(from_eof=False)
        if next_row >= 0:
            self.play_track(next_row, reason="next")
        else:
            self._log("NEXT: no playable track found")
            self.stop_playback()
        self._manual_nav_inflight = False

    @Slot()
    def play_previous(self) -> None:
        self._manual_nav_inflight = True
        self._transport_intent = "previous"
        self._ignore_eof_until = time.perf_counter() + 0.95
        self._suppress_auto_advance_until = time.perf_counter() + 0.95
        self._resolve_current_row(set_model=True)
        prev_row = self._previous_row(manual_nav=True)
        if prev_row >= 0:
            self.play_track(prev_row, reason="previous")
        else:
            self._log("PREV: no playable track found")
        self._manual_nav_inflight = False

    @Slot()
    def stop_playback(self) -> None:
        self._transport_intent = "stop"
        self._suppress_auto_advance_until = time.perf_counter() + 2.0
        self._ignore_eof_until = time.perf_counter() + 2.0
        self._eof_guard = True
        self._eof_watchdog_armed = False
        self.analyzer.stop(non_blocking=True)
        self.engine.stop()
        self._current_source = ""
        self.lbl_title.setText("STOPPED")
        self.lbl_source.setText("Stopped by user - playlist position preserved")
        self.track_label.setText("STOPPED · playlist position preserved")
        self._log("STOP: playback halted; EOF auto-advance suppressed")

    @Slot(bool)
    def _set_repeat(self, checked: bool) -> None:
        self._repeat = bool(checked)
        self._log(f"repeat-all {'enabled' if checked else 'disabled'}")

    @Slot(bool)
    def _set_shuffle(self, checked: bool) -> None:
        self._shuffle = bool(checked)
        self._play_history.clear()
        self._rebuild_shuffle_bag(exclude_current=True)
        self._log(f"shuffle {'enabled' if checked else 'disabled'}")

    @Slot(bool)
    def _seek_dragging_changed(self, dragging: bool) -> None:
        self._seek_dragging = bool(dragging)

    @Slot(int)
    def _seek_preview_changed(self, value: int) -> None:
        self.lbl_elapsed.setText(format_seconds(value / 1000.0))

    @Slot(int)
    def _seek_committed(self, value: int) -> None:
        if self._last_duration > 0:
            seconds = max(0.0, min(float(value) / 1000.0, self._last_duration))
            self._transport_intent = "seek"
            self._suppress_auto_advance_until = time.perf_counter() + 0.75
            self._ignore_eof_until = time.perf_counter() + 0.75
            self._eof_guard = False
            self._eof_watchdog_armed = False
            self.engine.seek_absolute(seconds)
            if self._current_source:
                QTimer.singleShot(80, lambda src=self._current_source, p=seconds: self._start_analyzer_if_current(src, p))

    @Slot(int)
    def _volume_changed(self, value: int) -> None:
        self.lbl_volume.setText(f"{value}%")
        self.engine.set_volume(value)

    @Slot(list)
    def _audio_outputs_changed(self, outputs: List[Dict[str, str]]) -> None:
        current = self.audio_output_combo.currentData() or self.settings.get("audio_output", "auto") or "auto"
        self._audio_outputs = outputs
        self.audio_output_combo.blockSignals(True)
        self.audio_output_combo.clear()
        for item in outputs:
            name = str(item.get("name") or "auto")
            desc = str(item.get("description") or name)
            label = desc if name == "auto" else f"{desc}"
            self.audio_output_combo.addItem(label, name)
        idx = self.audio_output_combo.findData(current)
        if idx < 0:
            idx = self.audio_output_combo.findData("auto")
        self.audio_output_combo.setCurrentIndex(max(0, idx))
        self.audio_output_combo.blockSignals(False)
        selected = self.audio_output_combo.currentData() or "auto"
        self.engine.set_audio_output(str(selected))

    @Slot(int)
    def _audio_output_selected(self, index: int) -> None:
        if index < 0:
            return
        device = self.audio_output_combo.itemData(index) or "auto"
        self.engine.set_audio_output(str(device))

    def _restart_playback_for_analyzer_change(self, reason: str) -> None:
        if self._loading_settings:
            return
        state = self._playback_state
        if state not in ("playing", "paused", "loading"):
            return
        row = self.playlist_model.current_row
        source = self._current_source
        if not source and row >= 0:
            track = self.playlist_model.track_at(row)
            source = track.source if track else ""
        if not source:
            return
        pos = max(0.0, float(self._last_position))
        was_paused = state == "paused"
        self._transport_intent = "analyzer-restart"
        self._suppress_auto_advance_until = time.perf_counter() + 2.5
        self._ignore_eof_until = time.perf_counter() + 2.5
        self._eof_guard = True
        self._eof_watchdog_armed = False
        self._log(f"{reason}: stopping/restarting playback at {format_seconds(pos)} to apply analyzer path")
        self.analyzer.stop(non_blocking=True)
        self.engine.stop()

        def resume_after_reconfigure() -> None:
            self._transport_intent = "play"
            self._suppress_auto_advance_until = 0.0
            self._ignore_eof_until = time.perf_counter() + 1.0
            self._eof_guard = False
            self._eof_watchdog_armed = False
            if row >= 0:
                self.playlist_model.set_current_row(row)
                track = self.playlist_model.track_at(row)
                if track:
                    self.lbl_title.setText(track.title)
                    self.lbl_source.setText(track.source)
                    self.track_label.setText("PLAYING · REAL FFT ACTIVE")
            self._current_source = source
            self._playback_state = "loading"
            self.analyzer_panel.set_state("loading")
            self.engine.load(source, pos)
            QTimer.singleShot(120, lambda src=source, p=pos: self._start_analyzer_if_current(src, p))
            if was_paused:
                QTimer.singleShot(620, self.engine.toggle_pause)

        QTimer.singleShot(180, resume_after_reconfigure)

    @Slot(int)
    def _analyzer_backend_selected(self, index: int) -> None:
        if index < 0:
            return
        backend = str(self.analyzer_backend_combo.itemData(index) or "auto")
        self.analyzer.set_backend(backend)
        self._log(f"analyzer backend selected: {backend}")
        self._restart_playback_for_analyzer_change("FFT backend changed")

    @Slot(int)
    def _fft_size_selected(self, index: int) -> None:
        if index < 0:
            return
        size = int(self.fft_size_combo.itemData(index) or 2048)
        self.analyzer.set_fft_size(size)
        self._log(f"FFT frame size selected: {size}")
        self._restart_playback_for_analyzer_change("FFT size changed")

    @Slot(int)
    def _bar_count_selected(self, index: int) -> None:
        if index < 0:
            return
        count = int(self.bar_count_combo.itemData(index) or 64)
        self.analyzer.set_bar_count(count)
        if hasattr(self.analyzer_panel, "set_bar_count"):
            try:
                self.analyzer_panel.set_bar_count(count)
            except Exception:
                pass
        self._log(f"spectrum bar count selected: {count}")
        self._restart_playback_for_analyzer_change("bar count changed")

    @Slot(int)
    def _render_fps_changed(self, index: int) -> None:
        if index < 0:
            return
        fps = int(self.render_fps_combo.itemData(index) or DEFAULT_RENDER_FPS)
        if fps not in RENDER_FPS_VALUES:
            fps = DEFAULT_RENDER_FPS
        self.analyzer.set_target_fps(fps)
        if hasattr(self.analyzer_panel, "set_render_fps"):
            try:
                self.analyzer_panel.set_render_fps(fps)
            except Exception:
                pass
        self._log(f"analyzer FPS target selected: {fps} fps")
        if not self._loading_settings:
            self._restart_playback_for_analyzer_change("FPS target changed")

    @Slot(int)
    def _spectrum_theme_selected(self, index: int) -> None:
        if index < 0:
            return
        theme = SPECTRUM_THEME_ALIASES.get(str(self.spectrum_theme_combo.itemData(index) or DEFAULT_SPECTRUM_THEME), str(self.spectrum_theme_combo.itemData(index) or DEFAULT_SPECTRUM_THEME))
        if hasattr(self.analyzer_panel, "set_theme"):
            try:
                self.analyzer_panel.set_theme(theme)
            except Exception:
                pass
        self._log(f"spectrum theme selected: {SPECTRUM_THEMES.get(theme, {}).get('name', theme)}")

    @Slot(int)
    def _spectrum_visual_selected(self, index: int) -> None:
        if index < 0:
            return
        mode = SPECTRUM_VISUAL_ALIASES.get(str(self.spectrum_visual_combo.itemData(index) or DEFAULT_SPECTRUM_VISUAL_MODE), str(self.spectrum_visual_combo.itemData(index) or DEFAULT_SPECTRUM_VISUAL_MODE))
        if hasattr(self.analyzer_panel, "set_visual_mode"):
            try:
                self.analyzer_panel.set_visual_mode(mode)
            except Exception:
                pass
        label = dict(SPECTRUM_VISUAL_MODES).get(mode, mode)
        self._log(f"spectrum visual selected: {label}")

    @Slot(str)
    def _source_changed(self, source: str) -> None:
        self._current_source = source
        self._log(f"source active: {source}")

    @Slot(str, float)
    def _duration_changed(self, source: str, duration: float) -> None:
        if source:
            self.playlist_model.update_duration_by_source(source, duration)

    @Slot(float, float)
    def _position_changed(self, pos: float, duration: float) -> None:
        self._last_position = pos
        self._last_duration = duration
        self.lbl_position.setText(f"{format_seconds(pos)} / {format_seconds(duration if duration > 0 else None)}")
        if self._show_remaining and duration > 0:
            remaining = pos - duration
            self.lbl_elapsed.setText(f"-{format_seconds(abs(remaining))}")
        else:
            self.lbl_elapsed.setText(format_seconds(pos))
        self.lbl_total.setText(format_seconds(duration if duration > 0 else None))
        self.seek_slider.set_duration_seconds(duration if duration > 0 else 0.0)
        if duration > 0:
            self.seek_slider.setRange(0, max(1, int(duration * 1000)))
            if not self._seek_dragging:
                self.seek_slider.setValue(max(0, min(int(pos * 1000), self.seek_slider.maximum())))
        else:
            if not self._seek_dragging:
                self.seek_slider.setRange(0, 1000)
                self.seek_slider.setValue(0)
        self.analyzer.update_mpv_position(pos, self._playback_state)
        self._arm_eof_watchdog_if_needed(pos, duration)

    def _arm_eof_watchdog_if_needed(self, pos: float, duration: float) -> None:
        if self._eof_guard or self._eof_watchdog_armed:
            return
        if time.perf_counter() < self._suppress_auto_advance_until:
            return
        if self._playback_state != "playing":
            return
        if duration <= 1.0:
            return
        if pos >= max(0.0, duration - 0.45):
            self._eof_watchdog_armed = True
            QTimer.singleShot(750, self._eof_watchdog_check)

    @Slot()
    def _eof_watchdog_check(self) -> None:
        self._eof_watchdog_armed = False
        if self._eof_guard or time.perf_counter() < self._suppress_auto_advance_until:
            return
        if self._last_duration > 1.0 and self._last_position >= max(0.0, self._last_duration - 0.60):
            self._log("EOF watchdog fallback triggered")
            self._handle_eof()

    @Slot(dict)
    def _metadata_changed(self, metadata: Dict[str, Any]) -> None:
        if not metadata:
            self.lbl_meta.setText("metadata: --")
            return
        artist = metadata.get("artist") or metadata.get("ARTIST") or ""
        album = metadata.get("album") or metadata.get("ALBUM") or ""
        title = metadata.get("title") or metadata.get("TITLE") or ""
        parts = [str(x) for x in (artist, album, title) if x]
        self.lbl_meta.setText("metadata: " + (" · ".join(parts[:3]) if parts else "available"))
        if title:
            display = f"{artist} — {title}" if artist else str(title)
            self.setWindowTitle(f"{display}  ·  {APP_NAME} {APP_VERSION}")
        if title and self.playlist_model.current_row >= 0:
            track = self.playlist_model.track_at(self.playlist_model.current_row)
            if track and track.title == title_from_source(track.source):
                track.title = str(title)
                self.playlist_model.dataChanged.emit(
                    self.playlist_model.index(self.playlist_model.current_row, 1),
                    self.playlist_model.index(self.playlist_model.current_row, 1),
                    [Qt.DisplayRole],
                )

    @Slot(str)
    def _state_changed(self, state: str) -> None:
        # mpv can emit idle/stopped while a new file is being loaded or while an
        # analyzer backend restart is in progress. Do not let that stale state stop
        # the analyzer worker before the first PCM frame arrives.
        now = time.perf_counter()
        stale_load_state = (
            state in ("idle", "stopped")
            and bool(self._current_source)
            and self._transport_intent in ("direct", "next", "previous", "eof", "play", "resume", "seek", "analyzer-restart")
            and now < self._ignore_eof_until
        )
        if stale_load_state:
            self._playback_state = "loading"
            self.state_led.set_state("loading")
            self.analyzer_panel.set_state("loading")
            self.analyzer.set_playback_state("loading")
            self.status_bar.showMessage("State: loading", 1000)
            self._log(f"stale mpv {state} ignored during {self._transport_intent} transition")
            return
        self._playback_state = state
        self.state_led.set_state(state)
        self.analyzer_panel.set_state(state)
        self.analyzer.set_playback_state(state)
        self.status_bar.showMessage(f"State: {state}", 1500)
        if state in ("idle", "stopped"):
            self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")

    @Slot()
    def _handle_eof(self) -> None:
        now = time.perf_counter()
        if self._eof_guard:
            return
        if now < self._suppress_auto_advance_until or self._transport_intent in ("stop", "analyzer-restart"):
            self._log(f"EOF ignored because transport intent is {self._transport_intent}")
            return
        if now < self._ignore_eof_until:
            self._log("stale EOF ignored during manual/load transition")
            return
        self._eof_guard = True
        self._eof_watchdog_armed = False

        # For live streams: retry the same source instead of advancing.
        current_row = self.playlist_model.current_row
        track = self.playlist_model.track_at(current_row)
        if track is not None and track.kind == "stream":
            if self._stream_reconnect_attempts < self._stream_reconnect_max:
                self._stream_reconnect_attempts += 1
                delay = min(8000, 1500 * self._stream_reconnect_attempts)
                self._log(
                    f"stream EOF: reconnect attempt {self._stream_reconnect_attempts}/"
                    f"{self._stream_reconnect_max} in {delay // 1000}s"
                )
                self.lbl_title.setText(
                    f"RECONNECTING ({self._stream_reconnect_attempts}/{self._stream_reconnect_max})…"
                )
                self.status_bar.showMessage(
                    f"Stream lost — reconnecting in {delay // 1000}s…", delay + 500
                )
                self._eof_guard = False
                QTimer.singleShot(delay, lambda: self._stream_reconnect(current_row))
                return
            else:
                self._stream_reconnect_attempts = 0
                self._log("stream reconnect exhausted; advancing playlist")

        self._log("EOF advance handler armed")
        QTimer.singleShot(70, self._handle_eof_advance)

    def _stream_reconnect(self, row: int) -> None:
        if self._transport_intent in ("stop",):
            return
        self._log(f"stream reconnect: retrying row {row + 1}")
        self._eof_guard = False
        self.play_track(row, reason="stream-reconnect")

    @Slot()
    def _handle_eof_advance(self) -> None:
        next_row = self._next_row(from_eof=True)
        if next_row >= 0:
            self._log(f"EOF -> next row {next_row + 1}")
            self.play_track(next_row, reason="eof")
        else:
            self._log("EOF -> stop; repeat disabled and playlist ended")
            self.stop_playback()

    @Slot(str)
    def _error(self, message: str) -> None:
        self._log("ERROR: " + message)
        self.status_bar.showMessage(message, 5000)

    def _heartbeat(self) -> None:
        jobs = len(self._scan_jobs)
        rows = self.playlist_model.rowCount()
        self.status_bar.showMessage(
            f"Playlist: {rows} item(s) | Scan jobs: {jobs} | Repeat: {'ON' if self._repeat else 'OFF'} | Shuffle: {'ON' if self._shuffle else 'OFF'}",
            900,
        )

    def _log(self, message: str) -> None:
        self.log_text.appendPlainText(f"[{now_stamp()}] {message}")

    @Slot()
    def toggle_playlist_panel(self) -> None:
        visible = not self.playlist_panel.isVisible()
        self.playlist_panel.setVisible(visible)
        if visible:
            self.main_splitter.setSizes([760, 690])
        self._log(f"playlist panel {'shown' if visible else 'hidden'}")

    @Slot()
    def toggle_log_panel(self) -> None:
        visible = not self.log_panel.isVisible()
        self.log_panel.setVisible(visible)
        self._log(f"log panel {'shown' if visible else 'hidden'}")

    @Slot()
    def toggle_mute(self) -> None:
        if self._is_muted:
            self._is_muted = False
            self.volume_slider.setValue(self._pre_mute_volume)
            self.btn_mute.setText("🔊")
        else:
            self._pre_mute_volume = self.volume_slider.value()
            self._is_muted = True
            self.volume_slider.setValue(0)
            self.btn_mute.setText("🔇")

    @Slot()
    def toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self.btn_fullscreen.setText("⛶")
            self._is_fullscreen = False
        else:
            self.showFullScreen()
            self.btn_fullscreen.setText("❎")
            self._is_fullscreen = True

    @Slot()
    def toggle_remaining_display(self) -> None:
        self._show_remaining = not self._show_remaining
        self._position_changed(self._last_position, self._last_duration)

    def _adjust_volume(self, delta: int) -> None:
        new_vol = max(0, min(130, self.volume_slider.value() + delta))
        self.volume_slider.setValue(new_vol)
        if self._is_muted and new_vol > 0:
            self._is_muted = False
            self.btn_mute.setText("🔊")

    def _toggle_repeat_shortcut(self) -> None:
        self.chk_repeat.setChecked(not self.chk_repeat.isChecked())

    def _toggle_shuffle_shortcut(self) -> None:
        self.chk_shuffle.setChecked(not self.chk_shuffle.isChecked())

    @Slot()
    def _smooth_speed_changed(self) -> None:
        preset = str(self.smooth_combo.currentData() or "medium")
        if hasattr(self.analyzer_panel, "set_smooth_speed"):
            self.analyzer_panel.set_smooth_speed(preset)

    @Slot()
    def _peak_decay_changed(self) -> None:
        preset = str(self.peak_decay_combo.currentData() or "medium")
        if hasattr(self.analyzer_panel, "set_peak_decay"):
            self.analyzer_panel.set_peak_decay(preset)

    @Slot()
    def _reset_peaks(self) -> None:
        if hasattr(self.analyzer_panel, "reset_peaks"):
            self.analyzer_panel.reset_peaks()

    @Slot()
    def open_config_folder(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(CONFIG_DIR)))

    @Slot()
    def about_dialog(self) -> None:
        import sys
        try:
            import PySide6
            pyside_ver = PySide6.__version__
        except Exception:
            pyside_ver = "unknown"
        try:
            import numpy as np
            numpy_ver = np.__version__
        except Exception:
            numpy_ver = "not installed"
        try:
            import mpv as _mpv
            mpv_ver = getattr(_mpv, "MPV_VERSION", None) or getattr(_mpv, "__version__", "installed")
        except Exception:
            mpv_ver = "unknown"
        try:
            import pyfftw
            pyfftw_ver = pyfftw.__version__
        except Exception:
            pyfftw_ver = "not installed"
        try:
            native = __import__("pytune_hfplus_native_fft")
            native_info = native.engine_info() if hasattr(native, "engine_info") else {}
            native_ver = "linked  (FFTW3f: {})".format("yes" if native_info.get("fftw3f") else "no")
        except Exception:
            native_ver = "not built"
        py_ver = "{}.{}.{}".format(*sys.version_info[:3])
        dlg = QDialog(self)
        dlg.setWindowTitle(f"About {APP_NAME}")
        dlg.setMinimumWidth(520)
        dlg.setModal(True)
        dlg.setStyleSheet(
            "QDialog { background:#1a1d22; border:1px solid #3a4050; border-radius:10px; }"
            "QLabel#about_body { color:#c8cdd6; font-size:10pt; font-family:monospace;"
            "  background:#111418; border:1px solid #2a3040; border-radius:6px; padding:14px; }"
            "QLabel#about_title { color:#f4f6fa; font-size:13pt; font-weight:700; }"
            "QLabel#about_sub { color:#888fa0; font-size:9pt; }"
            "QPushButton { background:#2a2f3a; color:#f4f6fa; border:1px solid #555e6a;"
            "  border-radius:6px; padding:8px 28px; font-size:10pt; font-weight:600; min-width:90px; }"
            "QPushButton:hover { background:#3a3f4d; border-color:#ff2d2d; color:#ffffff; }"
            "QPushButton:pressed { background:#ff2d2d; color:#ffffff; border-color:#ff2d2d; }"
        )
        v = QVBoxLayout(dlg)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(12)
        lbl_title = QLabel(f"{APP_NAME}  {APP_VERSION}")
        lbl_title.setObjectName("about_title")
        v.addWidget(lbl_title)
        lbl_sub = QLabel("Developed by TorZero  ·  Real-time MPV + FFT deck")
        lbl_sub.setObjectName("about_sub")
        v.addWidget(lbl_sub)
        body = (
            f"Runtime libraries\n"
            f"  Python          {py_ver}\n"
            f"  PySide6 / Qt6   {pyside_ver}\n"
            f"  python-mpv      {mpv_ver}\n"
            f"  NumPy           {numpy_ver}\n"
            f"  pyFFTW          {pyfftw_ver}\n"
            f"  Native FFT .so  {native_ver}\n"
            f"\n"
            f"Audio engine   mpv / libmpv\n"
            f"Analyzer       FFmpeg raw PCM → rFFT\n"
            f"FFT backends   Auto C++  ·  KissFFT  ·  PFFT  ·  FFTW  ·  NumPy\n"
            f"\n"
            f"Keyboard shortcuts\n"
            f"  Space          Play / Pause\n"
            f"  N / P          Next / Previous track\n"
            f"  M              Mute / Unmute\n"
            f"  + / -          Volume up / down\n"
            f"  R              Toggle Repeat All\n"
            f"  S              Toggle Shuffle\n"
            f"  F  or  F11     Fullscreen toggle\n"
            f"  Ctrl+→ / ←     Seek ±10 s\n"
            f"  Ctrl+O         Open file(s)\n"
            f"  Ctrl+Shift+O   Open folder\n"
            f"  Ctrl+U         Open URL / stream\n"
            f"  Del            Remove selected track(s)"
        )
        lbl_body = QLabel(body)
        lbl_body.setObjectName("about_body")
        lbl_body.setTextInteractionFlags(Qt.TextSelectableByMouse)
        v.addWidget(lbl_body)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(dlg.accept)
        btn_close.setDefault(True)
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)
        dlg.exec()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        urls = event.mimeData().urls()
        sources: List[str] = []
        folders: List[str] = []
        for url in urls:
            if url.isLocalFile():
                path = Path(url.toLocalFile())
                if path.is_dir():
                    folders.append(str(path))
                else:
                    sources.append(str(path))
            else:
                sources.append(url.toString())
        if sources:
            self._add_sources(sources)
        if folders:
            self.start_folder_scan(folders)
        event.acceptProposedAction()

    def closeEvent(self, event: Any) -> None:  # noqa: N802
        self._save_settings()
        self.analyzer.stop(non_blocking=True)
        for job in list(self._scan_jobs):
            worker = job.get("worker")
            thread = job.get("thread")
            try:
                if worker is not None:
                    worker.stop()
                if thread is not None:
                    thread.quit()
            except Exception:
                pass
        self.engine.shutdown()
        event.accept()


def install_exception_hook(window: Optional[MainWindow] = None) -> None:
    def hook(exc_type: Any, exc: BaseException, tb: Any) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        if window is not None:
            window._log("UNHANDLED EXCEPTION:\n" + text)
        else:
            print(text, file=sys.stderr)
    sys.excepthook = hook


def main() -> int:
    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(ORG_NAME)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    install_exception_hook(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
