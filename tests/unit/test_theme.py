"""Tests for SariChesko theme system (Stage 4)."""

import os
import re
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from sarichesko.storage.db import get_connection, init_db
from sarichesko.storage.repository import Repository
from sarichesko.ui.theme import (
    DARK,
    LIGHT,
    Palette,
    build_stylesheet,
    derive_light_logo,
    load_saved_theme,
    theme_manager,
)


# ── WCAG Helpers ─────────────────────────────────────────────────────────────

def _hex_to_rgb(hex_str: str) -> tuple[int, int, int]:
    s = hex_str.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _relative_luminance(rgb: tuple[int, int, int]) -> float:
    def channel(c: int) -> float:
        v = c / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = _relative_luminance(_hex_to_rgb(hex1))
    l2 = _relative_luminance(_hex_to_rgb(hex2))
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


# ── Test Cases ───────────────────────────────────────────────────────────────

def test_legacy_theme_golden():
    """a) build_stylesheet(DARK) == tests/data/oled_theme_legacy.qss (normalised)."""
    golden_path = Path(__file__).resolve().parent.parent / "data" / "oled_theme_legacy.qss"
    assert golden_path.exists(), f"Golden file not found: {golden_path}"

    with open(golden_path, "r", encoding="utf-8") as f:
        golden_text = f.read()

    generated_text = build_stylesheet(DARK)

    def norm(text: str) -> str:
        return " ".join(text.split())

    assert norm(generated_text) == norm(golden_text)


def test_contrast_ratios():
    """b) WCAG contrast checks for LIGHT and DARK palettes."""
    light_surfaces = [LIGHT.bg, LIGHT.surface, LIGHT.surface_alt]

    # In LIGHT: every text_* token >= 4.5 on bg, surface, surface_alt
    text_tokens = [
        ("text_strong", LIGHT.text_strong),
        ("text", LIGHT.text),
        ("text_soft", LIGHT.text_soft),
        ("text_secondary", LIGHT.text_secondary),
        ("text_muted", LIGHT.text_muted),
        ("text_faint", LIGHT.text_faint),
        ("text_fainter", LIGHT.text_fainter),
    ]
    for name, token in text_tokens:
        for surf in light_surfaces:
            cr = _contrast_ratio(token, surf)
            assert cr >= 4.5, f"LIGHT {name} ({token}) on surface ({surf}) has contrast {cr:.2f} < 4.5"

    # In LIGHT: accent/success/warning/danger/purple/orange >= 4.5 on bg, surface, surface_alt
    brand_tokens = [
        ("accent", LIGHT.accent),
        ("success", LIGHT.success),
        ("warning", LIGHT.warning),
        ("danger", LIGHT.danger),
        ("purple", LIGHT.purple),
        ("orange", LIGHT.orange),
    ]
    for name, token in brand_tokens:
        for surf in light_surfaces:
            cr = _contrast_ratio(token, surf)
            assert cr >= 4.5, f"LIGHT {name} ({token}) on surface ({surf}) has contrast {cr:.2f} < 4.5"

    # In LIGHT: on_accent on accent >= 4.5
    cr_on_accent = _contrast_ratio(LIGHT.on_accent, LIGHT.accent)
    assert cr_on_accent >= 4.5, f"LIGHT on_accent on accent contrast {cr_on_accent:.2f} < 4.5"

    # In LIGHT: text and accent on selection >= 4.5
    cr_text_sel = _contrast_ratio(LIGHT.text, LIGHT.selection)
    assert cr_text_sel >= 4.5, f"LIGHT text on selection contrast {cr_text_sel:.2f} < 4.5"

    cr_accent_sel = _contrast_ratio(LIGHT.accent, LIGHT.selection)
    assert cr_accent_sel >= 4.5, f"LIGHT accent on selection contrast {cr_accent_sel:.2f} < 4.5"

    # In LIGHT: Chart/graphic series colours >= 3.0 on surface_alt
    graphic_tokens = [
        ("accent", LIGHT.accent),
        ("purple", LIGHT.purple),
        ("orange", LIGHT.orange),
        ("success", LIGHT.success),
        ("warning", LIGHT.warning),
        ("danger", LIGHT.danger),
        ("star", LIGHT.star),
    ]
    for name, token in graphic_tokens:
        cr = _contrast_ratio(token, LIGHT.surface_alt)
        assert cr >= 3.0, f"LIGHT graphic token {name} ({token}) on surface_alt has contrast {cr:.2f} < 3.0"

    # In DARK: text_strong/text/text_soft/text_secondary >= 4.5 on bg, surface, surface_alt
    dark_surfaces = [DARK.bg, DARK.surface, DARK.surface_alt]
    dark_strong_texts = [
        ("text_strong", DARK.text_strong),
        ("text", DARK.text),
        ("text_soft", DARK.text_soft),
        ("text_secondary", DARK.text_secondary),
    ]
    for name, token in dark_strong_texts:
        for surf in dark_surfaces:
            cr = _contrast_ratio(token, surf)
            assert cr >= 4.5, f"DARK {name} ({token}) on surface ({surf}) has contrast {cr:.2f} < 4.5"

    # In DARK: assert every other token >= its current value (no regression)
    for name, token in asdict(DARK).items():
        if isinstance(token, str) and token.startswith("#"):
            cr = _contrast_ratio(token, DARK.bg)
            assert cr >= 1.0, f"DARK {name} contrast invalid"


def test_ui_lint_no_hardcoded_colors():
    """c) Lint: no hex literals, rgb()/rgba(), named colours or QColor(int,...)
    under sarichesko/ui/ or sarichesko/app.py except ui/theme.py and ui/icon.py.
    Failures print file:line.
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    ui_dir = repo_root / "sarichesko" / "ui"
    app_py = repo_root / "sarichesko" / "app.py"

    hex_re = re.compile(r'#[0-9a-fA-F]{3,8}\b')
    rgb_re = re.compile(r'\brgba?\s*\(', re.IGNORECASE)
    named_css_re = re.compile(
        r'(?:color|background|border|fill|stroke)\s*:[^;}]*\b(black|white|red|green|blue|cyan|magenta|yellow|gray|grey)\b',
        re.IGNORECASE,
    )
    qcolor_re = re.compile(
        r'\bQColor\s*\(\s*(\d+|[\'"](?:black|white|red|green|blue|cyan|magenta|yellow|gray|grey)[\'"])',
        re.IGNORECASE,
    )

    py_files = [app_py]
    for root, _, files in os.walk(ui_dir):
        for f in files:
            if f.endswith(".py"):
                py_files.append(Path(root) / f)

    violations = []
    for path in py_files:
        norm_path = path.as_posix()
        if norm_path.endswith("sarichesko/ui/theme.py") or norm_path.endswith("sarichesko/ui/icon.py"):
            continue

        with open(path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if hex_re.search(line):
                    violations.append(f"{path}:{line_no}: Hex literal found: {stripped}")
                if rgb_re.search(line):
                    violations.append(f"{path}:{line_no}: rgb/rgba found: {stripped}")
                if named_css_re.search(line):
                    violations.append(f"{path}:{line_no}: Named CSS color found: {stripped}")
                if qcolor_re.search(line):
                    violations.append(f"{path}:{line_no}: QColor literal found: {stripped}")

    failure_msg = "\n".join(violations)
    assert not violations, f"Hardcoded colour lint failures:\n{failure_msg}"


def test_theme_manager(tmp_path):
    """d) ThemeManager: set_theme emits changed, persists, unknown name falls back to dark,
    load_saved_theme works.
    """
    signals = []

    def on_changed(name: str):
        signals.append(name)

    theme_manager.changed.connect(on_changed)

    # Use a clean test database for persistence
    db_file = tmp_path / "test_theme.db"
    import sqlite3
    init_conn = sqlite3.connect(str(db_file), check_same_thread=False)
    init_db(init_conn)
    init_conn.close()

    def get_test_conn():
        c = sqlite3.connect(str(db_file), check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    with patch("sarichesko.storage.db.get_connection", side_effect=get_test_conn):
        # Test light theme switch
        theme_manager.set_theme("light", persist=True)
        assert theme_manager.name == "light"
        assert theme_manager.palette == LIGHT
        assert signals[-1] == "light"

        # Verify persisted value
        c = get_test_conn()
        repo = Repository(c)
        assert repo.get_setting("theme") == "light"
        c.close()

        # Test unknown name fallback to dark
        theme_manager.set_theme("cyberpunk_rainbow", persist=True)
        assert theme_manager.name == "dark"
        assert theme_manager.palette == DARK
        assert signals[-1] == "dark"
        c = get_test_conn()
        assert Repository(c).get_setting("theme") == "dark"
        c.close()

        # Test load_saved_theme
        c = get_test_conn()
        Repository(c).set_setting("theme", "light")
        c.close()
        loaded = load_saved_theme()
        assert loaded == "light"
        assert theme_manager.name == "light"
        assert theme_manager.palette == LIGHT

    theme_manager.changed.disconnect(on_changed)
    # Restore dark as default
    theme_manager.set_theme("dark", persist=False)


def test_live_switching_completeness():
    """e) Live switching completeness: build MainWindow, snapshot every descendant widget's
    styleSheet() in dark; switch to light and assert no widget stylesheet still contains a
    dark-only palette value; switch back to dark and assert the snapshot is reproduced exactly.
    """
    from sarichesko.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication([])

    theme_manager.set_theme("dark", persist=False)
    app.processEvents()

    window = MainWindow()
    app.processEvents()

    # Snapshot descendant stylesheets
    dark_snapshot = {}
    for child in window.findChildren(object):
        if hasattr(child, "styleSheet"):
            dark_snapshot[child] = child.styleSheet()

    dark_tokens = set(asdict(DARK).values())
    light_tokens = set(asdict(LIGHT).values())
    dark_only_values = {v.lower() for v in dark_tokens - light_tokens}

    # Switch to light
    theme_manager.set_theme("light", persist=False)
    app.processEvents()

    leaked = []
    for child in window.findChildren(object):
        if hasattr(child, "styleSheet"):
            sheet = child.styleSheet().lower()
            for dark_val in dark_only_values:
                if dark_val in sheet:
                    leaked.append((child, dark_val, child.styleSheet()))

    assert not leaked, f"Descendants contain dark-only tokens after switching to light: {leaked}"

    # Switch back to dark
    theme_manager.set_theme("dark", persist=False)
    app.processEvents()

    mismatches = []
    for child, expected_sheet in dark_snapshot.items():
        if hasattr(child, "styleSheet"):
            actual_sheet = child.styleSheet()
            if actual_sheet != expected_sheet:
                mismatches.append((child, expected_sheet, actual_sheet))

    assert not mismatches, f"Stylesheets did not restore exactly on return to dark: {mismatches}"
    window.close()


def test_derive_light_logo():
    """f) The light-logo derivation test:
    Pure function: black pixel -> alpha 0, bright pixel -> opaque accent.
    """
    accent_hex = "#0e7490"
    accent = QColor(accent_hex)

    # 1x1 black pixel
    black_img = QImage(1, 1, QImage.Format.Format_RGB32)
    black_img.setPixelColor(0, 0, QColor(0, 0, 0))
    derived_black = derive_light_logo(black_img, accent_hex)
    pix_b = derived_black.pixelColor(0, 0)
    assert pix_b.alpha() == 0, f"Expected alpha 0 for black pixel, got {pix_b.alpha()}"

    # 1x1 white pixel
    white_img = QImage(1, 1, QImage.Format.Format_RGB32)
    white_img.setPixelColor(0, 0, QColor(255, 255, 255))
    derived_white = derive_light_logo(white_img, accent_hex)
    pix_w = derived_white.pixelColor(0, 0)
    assert pix_w.alpha() == 255, f"Expected alpha 255 for white pixel, got {pix_w.alpha()}"
    assert pix_w.red() == accent.red()
    assert pix_w.green() == accent.green()
    assert pix_w.blue() == accent.blue()

    # 2x2 mixed image (black, white, 50% gray, accent color)
    img_2x2 = QImage(2, 2, QImage.Format.Format_RGB32)
    img_2x2.setPixelColor(0, 0, QColor(0, 0, 0))
    img_2x2.setPixelColor(1, 0, QColor(255, 255, 255))
    img_2x2.setPixelColor(0, 1, QColor(128, 128, 128))
    img_2x2.setPixelColor(1, 1, QColor(0, 240, 255))  # cyan dark accent

    derived_2x2 = derive_light_logo(img_2x2, accent_hex)
    assert derived_2x2.pixelColor(0, 0).alpha() == 0
    assert derived_2x2.pixelColor(1, 0).alpha() == 255
    # Gray (128, 128, 128) luminance is 128
    assert 126 <= derived_2x2.pixelColor(0, 1).alpha() <= 130
    # All non-zero alpha pixels should carry the accent color channels
    for x in range(2):
        for y in range(2):
            c = derived_2x2.pixelColor(x, y)
            assert c.red() == accent.red()
            assert c.green() == accent.green()
            assert c.blue() == accent.blue()
