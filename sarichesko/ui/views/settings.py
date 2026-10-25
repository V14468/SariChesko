import platform
import sys
from typing import Callable, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QGraphicsOpacityEffect, QScrollArea,
    QMessageBox, QApplication,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve

from ...platform import get_monitor, get_controller
from ...storage.db import get_connection, get_db_path, init_db
from ...storage.repository import Repository
from ..theme import theme_manager, Palette, style


SENSITIVITY_OPTIONS = [
    ("Conservative (flags less)", "0.75"),
    ("Balanced (default)", "1.0"),
    ("Aggressive (flags more)", "1.5"),
]


def _card() -> QFrame:
    """Create a styled card frame matching the app's existing visual language."""
    frame = QFrame()
    frame.setObjectName("card")
    return frame


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    style(
        lbl,
        lambda p: (
            f"font-size: 11px; font-weight: 700; color: {p.text_muted}; "
            "letter-spacing: 0.8px; text-transform: uppercase;"
        ),
    )
    return lbl


def _body_label(text: str, color_fn: Optional[Callable[[Palette], str]] = None) -> QLabel:
    lbl = QLabel(text)
    if color_fn is None:
        color_fn = lambda p: p.text
    style(lbl, lambda p: f"font-size: 13px; color: {color_fn(p)};")
    lbl.setWordWrap(True)
    return lbl


def _action_button(text: str, color_fn: Callable[[Palette], str]) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedHeight(34)
    style(btn, lambda p: f"""
        QPushButton {{
            background-color: {p.surface};
            color: {color_fn(p)};
            border: 1px solid {color_fn(p)};
            border-radius: 8px;
            padding: 6px 18px;
            font-size: 12px;
            font-weight: 700;
        }}
        QPushButton:hover {{
            background-color: {p.selection};
        }}
    """)
    return btn


class SettingsView(QWidget):
    def __init__(self):
        super().__init__()
        self._monitor = get_monitor()
        self._controller = get_controller()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        style(scroll, lambda p: f"QScrollArea {{ background: {p.bg}; border: none; }}")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # Page header
        title = QLabel("Settings")
        style(title, lambda p: f"font-size: 26px; font-weight: 800; color: {p.text_strong};")
        subtitle = QLabel("Preferences, privilege status, local data, and about")
        style(subtitle, lambda p: f"font-size: 13px; color: {p.text_muted};")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # ── Card 1: Privilege Status ──────────────────────────────────
        priv_card = _card()
        priv_layout = QVBoxLayout(priv_card)
        priv_layout.setContentsMargins(20, 16, 20, 16)
        priv_layout.setSpacing(8)
        priv_layout.addWidget(_section_title("PRIVILEGE STATUS"))

        elevated = self._controller.is_elevated()
        if sys.platform == "win32":
            status_text = f"Running as Administrator: {'Yes' if elevated else 'No'}"
        else:
            status_text = f"Running as root: {'Yes' if elevated else 'No'}"
        self._priv_status = _body_label(
            status_text,
            lambda p: p.success if elevated else p.warning,
        )
        priv_layout.addWidget(self._priv_status)

        priv_layout.addWidget(_body_label(
            "Only applying real network fixes requires elevation. Diagnostics, "
            "simulation, algorithm comparison, and monitoring never need it.",
            lambda p: p.text_muted,
        ))

        self._priv_msg = _body_label("", lambda p: p.warning)
        self._priv_msg.setVisible(False)
        self._btn_elevate = QPushButton("Restart as Administrator")
        self._btn_elevate.setObjectName("primary_btn")
        self._btn_elevate.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_elevate.setFixedHeight(34)
        self._btn_elevate.clicked.connect(self._on_restart_elevated)

        if elevated:
            priv_layout.addWidget(_body_label(
                "Elevation is on for this session. It can't be switched off in place \u2014 "
                "close SariChesko and open it normally to run without it.",
                lambda p: p.text_muted,
            ))
        elif self._controller.can_relaunch_elevated():
            elev_row = QHBoxLayout()
            elev_row.addWidget(self._btn_elevate)
            elev_row.addStretch()
            priv_layout.addLayout(elev_row)
        else:
            priv_layout.addWidget(_body_label(
                self._controller.relaunch_elevated().message,
                lambda p: p.text_muted,
            ))
            self._btn_elevate.setVisible(False)
        priv_layout.addWidget(self._priv_msg)
        layout.addWidget(priv_card)

        # ── Card 2: Appearance ────────────────────────────────────────
        app_card = _card()
        app_layout = QVBoxLayout(app_card)
        app_layout.setContentsMargins(20, 16, 20, 16)
        app_layout.setSpacing(10)
        app_layout.addWidget(_section_title("APPEARANCE"))

        theme_row = QHBoxLayout()
        theme_row.addWidget(_body_label("Theme"))
        self._theme_combo = QComboBox()
        self._theme_combo.setFixedWidth(220)
        self._theme_combo.setFixedHeight(32)
        self._theme_combo.addItem("Dark (default)", "dark")
        self._theme_combo.addItem("Light", "light")
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_row.addStretch()
        theme_row.addWidget(self._theme_combo)
        app_layout.addLayout(theme_row)

        layout.addWidget(app_card)

        # ── Card 3: Preferences ───────────────────────────────────────
        pref_card = _card()
        pref_layout = QVBoxLayout(pref_card)
        pref_layout.setContentsMargins(20, 16, 20, 16)
        pref_layout.setSpacing(10)
        pref_layout.addWidget(_section_title("PREFERENCES"))

        # Default interface
        iface_row = QHBoxLayout()
        iface_row.addWidget(_body_label("Default interface"))
        self._iface_combo = QComboBox()
        self._iface_combo.setFixedWidth(220)
        self._iface_combo.setFixedHeight(32)
        try:
            ifaces = self._monitor.get_interfaces()
            for iface in ifaces:
                if iface.is_up:
                    label = f"{iface.name}"
                    if iface.speed_mbps:
                        label += f" ({iface.speed_mbps:.0f} Mbps)"
                    self._iface_combo.addItem(label, iface.name)
        except Exception:
            self._iface_combo.addItem("No interfaces found")
        self._iface_combo.currentIndexChanged.connect(self._on_default_iface_changed)
        iface_row.addStretch()
        iface_row.addWidget(self._iface_combo)
        pref_layout.addLayout(iface_row)

        # Congestion sensitivity
        sens_row = QHBoxLayout()
        sens_row.addWidget(_body_label("Congestion sensitivity"))
        self._sens_combo = QComboBox()
        self._sens_combo.setFixedWidth(220)
        self._sens_combo.setFixedHeight(32)
        for label_text, value in SENSITIVITY_OPTIONS:
            self._sens_combo.addItem(label_text, value)
        self._sens_combo.currentIndexChanged.connect(self._on_sensitivity_changed)
        sens_row.addStretch()
        sens_row.addWidget(self._sens_combo)
        pref_layout.addLayout(sens_row)

        layout.addWidget(pref_card)

        # ── Card 4: Local Data ────────────────────────────────────────
        data_card = _card()
        data_layout = QVBoxLayout(data_card)
        data_layout.setContentsMargins(20, 16, 20, 16)
        data_layout.setSpacing(10)
        data_layout.addWidget(_section_title("LOCAL DATA"))

        self._db_path_label = _body_label(f"Database: {get_db_path()}", lambda p: p.text_secondary)
        data_layout.addWidget(self._db_path_label)

        self._counts_label = _body_label("", lambda p: p.text_secondary)
        data_layout.addWidget(self._counts_label)

        btn_row = QHBoxLayout()
        self._btn_clear_history = _action_button("Clear History", lambda p: p.warning)
        self._btn_clear_history.clicked.connect(self._clear_history)
        btn_row.addWidget(self._btn_clear_history)

        self._btn_reset_baselines = _action_button("Reset Baselines", lambda p: p.danger)
        self._btn_reset_baselines.clicked.connect(self._clear_baselines)
        btn_row.addWidget(self._btn_reset_baselines)
        btn_row.addStretch()
        data_layout.addLayout(btn_row)

        layout.addWidget(data_card)

        # ── Card 5: About ─────────────────────────────────────────────
        about_card = _card()
        about_layout = QVBoxLayout(about_card)
        about_layout.setContentsMargins(20, 16, 20, 16)
        about_layout.setSpacing(6)
        about_layout.addWidget(_section_title("ABOUT"))

        from sarichesko import __version__
        about_layout.addWidget(_body_label(f"SariChesko v{__version__}", lambda p: p.accent))

        import PySide6
        about_layout.addWidget(_body_label(
            f"OS: {platform.system()} {platform.release()}\n"
            f"Python: {platform.python_version()}\n"
            f"PySide6: {PySide6.__version__}",
            lambda p: p.text_secondary,
        ))
        layout.addWidget(about_card)

        layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        # Fade in
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._anim = QPropertyAnimation(self._opacity, b"opacity")
        self._anim.setDuration(350)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

        # Load persisted settings
        self._load_settings()

    # ── Lifecycle ──────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self._load_settings()

    # ── Settings persistence ──────────────────────────────────────────

    def _load_settings(self):
        try:
            conn = get_connection()
            init_db(conn)
            repo = Repository(conn)

            # Default interface
            saved_iface = repo.get_setting("default_interface", "")
            if saved_iface:
                for i in range(self._iface_combo.count()):
                    if self._iface_combo.itemData(i) == saved_iface:
                        self._iface_combo.blockSignals(True)
                        self._iface_combo.setCurrentIndex(i)
                        self._iface_combo.blockSignals(False)
                        break

            # Sensitivity
            saved_sens = repo.get_setting("congestion_sensitivity", "1.0")
            for i in range(self._sens_combo.count()):
                if self._sens_combo.itemData(i) == saved_sens:
                    self._sens_combo.blockSignals(True)
                    self._sens_combo.setCurrentIndex(i)
                    self._sens_combo.blockSignals(False)
                    break

            # Theme
            saved_theme = repo.get_setting("theme", theme_manager.name)
            for i in range(self._theme_combo.count()):
                if self._theme_combo.itemData(i) == saved_theme:
                    self._theme_combo.blockSignals(True)
                    self._theme_combo.setCurrentIndex(i)
                    self._theme_combo.blockSignals(False)
                    break

            # Data counts
            counts = repo.get_history_counts()
            self._counts_label.setText(
                f"Sessions: {counts.get('sessions', 0)}  ·  "
                f"Measurements: {counts.get('measurements', 0)}  ·  "
                f"Diagnostic runs: {counts.get('diagnostic_runs', 0)}  ·  "
                f"Simulations: {counts.get('simulation_results', 0)}  ·  "
                f"Applied fixes: {counts.get('applied_policies', 0)}  ·  "
                f"Baselines: {counts.get('baselines', 0)}"
            )

            conn.close()
        except Exception:
            pass

    def _on_theme_changed(self, index: int):
        theme_name = self._theme_combo.itemData(index)
        if theme_name:
            theme_manager.set_theme(theme_name, persist=True)

    def _on_default_iface_changed(self, index: int):
        iface_name = self._iface_combo.itemData(index)
        if iface_name:
            try:
                conn = get_connection()
                init_db(conn)
                repo = Repository(conn)
                repo.set_setting("default_interface", iface_name)
                conn.close()
            except Exception:
                pass

    def _on_sensitivity_changed(self, index: int):
        value = self._sens_combo.itemData(index)
        if value:
            try:
                conn = get_connection()
                init_db(conn)
                repo = Repository(conn)
                repo.set_setting("congestion_sensitivity", value)
                conn.close()
            except Exception:
                pass

    def _on_restart_elevated(self):
        reply = QMessageBox.question(
            self, "Restart as Administrator?",
            "SariChesko will close and reopen with Administrator rights so it can apply "
            "network fixes. Windows will ask you to confirm. Your history, baselines and "
            "settings are kept.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = self._controller.relaunch_elevated()
        p = theme_manager.palette
        color = p.success if result.success else p.warning
        self._priv_msg.setStyleSheet(f"font-size: 13px; color: {color};")
        self._priv_msg.setText(result.message)
        self._priv_msg.setVisible(True)
        if result.success:
            QApplication.quit()

    def _clear_history(self):
        reply = QMessageBox.question(
            self, "Clear History",
            "This will permanently delete all diagnostic runs, measurements, "
            "simulation results, applied policies, ISP diagnostics, and sessions.\n\n"
            "Baselines and settings will be kept.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            conn = get_connection()
            init_db(conn)
            repo = Repository(conn)
            repo.clear_history()
            conn.close()
        except Exception:
            pass
        self._load_settings()

    def _clear_baselines(self):
        reply = QMessageBox.question(
            self, "Reset Baselines",
            "This will delete all saved interface baselines.\n\n"
            "You'll need to re-run diagnostics to establish new baselines.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            conn = get_connection()
            init_db(conn)
            repo = Repository(conn)
            repo.clear_baselines()
            conn.close()
        except Exception:
            pass
        self._load_settings()