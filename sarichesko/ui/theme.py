"""SariChesko Theme System: Token-based theme management, palette definitions,
stylesheet builder, and dynamic runtime restyling.
"""

from dataclasses import dataclass
from typing import Callable, Optional
import weakref
import re

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication, QWidget


@dataclass(frozen=True)
class Palette:
    # ── Core tokens ──
    bg: str                # Window background
    surface: str           # Cards, base button backgrounds
    surface_alt: str       # Inputs, tables, chart background
    surface_raised: str    # Dialogs background
    track: str             # Progress / gauge tracks, borders
    selection: str         # Hover / selected rows
    border: str            # Standard border
    border_strong: str     # Strong / button border
    text_strong: str       # High-contrast titles / text
    text: str              # Primary body text
    text_soft: str         # Soft text
    text_secondary: str    # Subtitles, descriptions
    text_muted: str        # Muted text, captions
    text_faint: str        # Subtle labels, hints
    text_fainter: str      # Very faint text
    accent: str            # Primary brand accent (cyan in dark, deep cyan in light)
    accent_hover: str      # Accent hover state
    on_accent: str         # Text on accent-filled buttons
    success: str           # Success / healthy / codel
    warning: str           # Warning / medium / RED
    danger: str            # Danger / high / critical
    purple: str            # Token bucket / accent variant
    orange: str            # Gauge high-severity arc / warning accent

    # ── Extra tokens for UI literals ──
    danger_hover: str
    danger_bg: str
    danger_border: str
    danger_bg_hover: str
    warning_bg: str
    dialog_btn: str
    nav_hover: str
    surface_hover: str
    splash_bg: str
    splash_border: str
    welcome_card_bg: str
    welcome_card_border: str
    star: str
    chart_grid: str


DARK = Palette(
    bg="#000000",
    surface="#080a10",
    surface_alt="#05060a",
    surface_raised="#0a0b10",
    track="#121420",
    selection="#0c1424",
    border="#121524",
    border_strong="#1a1d2e",
    text_strong="#ffffff",
    text="#e2e8f0",
    text_soft="#cbd5e1",
    text_secondary="#94a3b8",
    text_muted="#64748b",
    text_faint="#475569",
    text_fainter="#334155",
    accent="#00f0ff",
    accent_hover="#33f3ff",
    on_accent="#000000",
    success="#00e5a3",
    warning="#f59e0b",
    danger="#ef4444",
    purple="#a78bfa",
    orange="#f97316",
    # Extra tokens
    danger_hover="#f87171",
    danger_bg="#1a0f12",
    danger_border="#3f1d22",
    danger_bg_hover="#2a1216",
    warning_bg="#1a1500",
    dialog_btn="#12141c",
    nav_hover="#0a0d16",
    surface_hover="#0e1222",
    splash_bg="#050509",
    splash_border="#1e2030",
    welcome_card_bg="#060810",
    welcome_card_border="#141824",
    star="#facc15",
    chart_grid="#141828",
)

LIGHT = Palette(
    bg="#f1f5f9",
    surface="#ffffff",
    surface_alt="#f8fafc",
    surface_raised="#ffffff",
    track="#e2e8f0",
    selection="#e0f2fe",
    border="#e2e8f0",
    border_strong="#cbd5e1",
    text_strong="#0f172a",
    text="#1e293b",
    text_soft="#334155",
    text_secondary="#475569",
    text_muted="#566478",
    text_faint="#5f6e83",
    text_fainter="#5f6e83",
    accent="#0e7490",
    accent_hover="#155e75",
    on_accent="#ffffff",
    success="#047857",
    warning="#a85d08",
    danger="#b91c1c",
    purple="#6d28d9",
    orange="#c2410c",
    # Extra tokens
    danger_hover="#991b1b",
    danger_bg="#fef2f2",
    danger_border="#fecaca",
    danger_bg_hover="#fee2e2",
    warning_bg="#fffbeb",
    dialog_btn="#f1f5f9",
    nav_hover="#f1f5f9",
    surface_hover="#e2e8f0",
    splash_bg="#f8fafc",
    splash_border="#cbd5e1",
    welcome_card_bg="#ffffff",
    welcome_card_border="#e2e8f0",
    star="#b45309",
    chart_grid="#e2e8f0",
)


def build_stylesheet(p: Palette) -> str:
    """Generate the global application stylesheet from palette tokens."""
    return f"""
QMainWindow {{
    background-color: {p.bg};
}}
QWidget {{
    background-color: {p.bg};
    color: {p.text_strong};
    font-family: "Segoe UI", "Inter", -apple-system, sans-serif;
    font-size: 13px;
}}
QWidget:focus {{
    outline: none;
}}
QLabel {{
    color: {p.text_strong};
    background: transparent;
    padding: 2px 0px;
}}
QLabel#hero_title {{
    font-size: 42px;
    font-weight: 800;
    color: {p.accent};
    letter-spacing: 1.5px;
    padding-bottom: 4px;
}}
QLabel#hero_subtitle {{
    font-size: 15px;
    font-weight: 500;
    color: {p.text_secondary};
    line-height: 1.6;
}}
QLabel#sidebar_logo {{
    font-size: 22px;
    font-weight: 800;
    color: {p.accent};
    letter-spacing: 1px;
    padding: 4px 0px;
}}
QLabel#sidebar_tagline {{
    font-size: 11px;
    font-weight: 600;
    color: {p.text_muted};
    letter-spacing: 0.5px;
    padding-bottom: 8px;
}}

/* Sidebar Container */
QFrame#sidebar {{
    background-color: {p.bg};
    border-right: 1px solid {p.track};
}}

/* Navigation Buttons with High Visibility & Line Heights */
QPushButton#nav_button {{
    text-align: left;
    padding: 12px 18px;
    border: none;
    outline: none;
    border-radius: 8px;
    margin: 3px 8px;
    font-size: 13px;
    font-weight: 600;
    color: {p.text_secondary};
    background-color: transparent;
}}
QPushButton#nav_button:focus {{
    outline: none;
}}
QPushButton#nav_button:hover {{
    background-color: {p.nav_hover};
    color: {p.accent};
}}
QPushButton#nav_button:checked {{
    background-color: {p.selection};
    color: {p.accent};
    font-weight: 700;
    border-left: 4px solid {p.accent};
}}

/* General Buttons */
QPushButton {{
    background-color: {p.surface};
    color: {p.text_strong};
    border: 1px solid {p.border_strong};
    outline: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 600;
    min-height: 20px;
}}
QPushButton:focus {{
    outline: none;
}}
QPushButton:hover {{
    background-color: {p.surface_hover};
    border-color: {p.accent};
    color: {p.accent};
}}
QPushButton:pressed {{
    background-color: {p.accent};
    color: {p.on_accent};
}}
QPushButton#primary_btn {{
    background-color: {p.accent};
    color: {p.on_accent};
    border: none;
    font-weight: 700;
}}
QPushButton#primary_btn:hover {{
    background-color: {p.accent_hover};
    color: {p.on_accent};
}}

/* Glassmorphism / AMOLED Cards */
QFrame#card {{
    background-color: {p.surface_alt};
    border: 1px solid {p.border};
    border-radius: 12px;
    padding: 16px;
}}
QFrame#card:hover {{
    border-color: {p.accent};
}}
"""


# Backward-compatible global QSS alias
OLED_BLACK_THEME = build_stylesheet(DARK)

# Backward-compatible colour aliases
COLOR_AMOLED = DARK.bg
COLOR_CYAN = DARK.accent
COLOR_EMERALD = DARK.success
COLOR_TEXT_PRIMARY = DARK.text_strong
COLOR_TEXT_MUTED = DARK.text_secondary


class ThemeManager(QObject):
    changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._name: str = "dark"
        self._palette: Palette = DARK

    @property
    def name(self) -> str:
        return self._name

    @property
    def palette(self) -> Palette:
        return self._palette

    def set_theme(self, name: str, persist: bool = True) -> None:
        target = "light" if name == "light" else "dark"
        self._name = target
        self._palette = LIGHT if target == "light" else DARK

        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(build_stylesheet(self._palette))

        if persist:
            try:
                from ..storage.db import get_connection, init_db
                from ..storage.repository import Repository
                conn = get_connection()
                init_db(conn)
                Repository(conn).set_setting("theme", target)
                conn.close()
            except Exception:
                pass

        self.changed.emit(target)


# Global singleton instance
theme_manager = ThemeManager()


def load_saved_theme() -> str:
    """Read saved theme preference from DB and initialize theme_manager.

    Defaults to 'dark' on any error or missing setting.
    """
    theme_name = "dark"
    try:
        from ..storage.db import get_connection, init_db
        from ..storage.repository import Repository
        conn = get_connection()
        init_db(conn)
        theme_name = Repository(conn).get_setting("theme", "dark")
        conn.close()
    except Exception:
        theme_name = "dark"

    if theme_name not in ("dark", "light"):
        theme_name = "dark"

    theme_manager.set_theme(theme_name, persist=False)
    return theme_name


# ── Widget Restyling Helper ──
_styled_widgets: list[tuple[weakref.ref, Callable[[Palette], str]]] = []


def _on_theme_changed(_name: str) -> None:
    alive: list[tuple[weakref.ref, Callable[[Palette], str]]] = []
    p = theme_manager.palette
    for ref, fn in _styled_widgets:
        w = ref()
        if w is not None:
            try:
                w.setStyleSheet(fn(p))
                alive.append((ref, fn))
            except RuntimeError:
                pass
    _styled_widgets[:] = alive


theme_manager.changed.connect(_on_theme_changed)


def style(widget: QWidget, fn: Callable[[Palette], str]) -> None:
    """Set a widget's stylesheet dynamically from palette tokens and
    register it for automatic re-application on theme changes.
    """
    widget.setStyleSheet(fn(theme_manager.palette))
    # Filter dead refs and update existing ref if present
    alive: list[tuple[weakref.ref, Callable[[Palette], str]]] = []
    found = False
    for ref, old_fn in _styled_widgets:
        w = ref()
        if w is None:
            continue
        if w is widget:
            alive.append((ref, fn))
            found = True
        else:
            alive.append((ref, old_fn))
    if not found:
        alive.append((weakref.ref(widget), fn))
    _styled_widgets[:] = alive


# ── Welcome Screen Light Logo Derivation ──
def derive_light_logo(source_image: QImage, accent_hex: str) -> QImage:
    """Derive a transparent, accent-tinted QImage from an opaque dark source image.

    - Alpha is set to the luminance of each source pixel (black -> 0, bright -> 255).
    - Color channels are set to the accent color.
    """
    src = source_image.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = src.width(), src.height()
    accent = QColor(accent_hex)
    ar, ag, ab = accent.red(), accent.green(), accent.blue()

    try:
        import numpy as np
        ptr = src.constBits()
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((h, src.bytesPerLine() // 4, 4))[:, :w, :].copy()
        lum = np.clip(np.rint(0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]), 0, 255).astype(np.uint8)
        out = np.empty((h, w, 4), dtype=np.uint8)
        out[:, :, 0] = ar
        out[:, :, 1] = ag
        out[:, :, 2] = ab
        out[:, :, 3] = lum
        return QImage(out.data, w, h, w * 4, QImage.Format.Format_RGBA8888).copy()
    except ImportError:
        # Fallback pure-Qt pixel loop
        dest = QImage(w, h, QImage.Format.Format_ARGB32)
        dest.fill(0)
        for y in range(h):
            for x in range(w):
                sc = src.pixelColor(x, y)
                lum_val = int(round(0.2126 * sc.red() + 0.7152 * sc.green() + 0.0722 * sc.blue()))
                lum_val = max(0, min(255, lum_val))
                dest.setPixelColor(x, y, QColor(ar, ag, ab, lum_val))
        return dest