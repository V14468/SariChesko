import json
import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QGraphicsOpacityEffect, QStackedWidget,
    QFileDialog, QScrollArea,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve

from ...storage.db import get_connection, init_db
from ...storage.repository import Repository
from ...utils.export import export_rows_to_csv, default_export_dir
from ..theme import theme_manager, Palette, style


def table_style(p: Palette) -> str:
    return f"""
QTableWidget {{
    background-color: {p.surface_alt};
    color: {p.text};
    border: none;
    gridline-color: {p.border};
    font-size: 12px;
    selection-background-color: {p.selection};
    selection-color: {p.accent};
}}
QTableWidget::item {{
    padding: 6px;
    border-bottom: 1px solid {p.border};
}}
QHeaderView::section {{
    background-color: {p.surface_alt};
    color: {p.text_muted};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    border: none;
    border-bottom: 1px solid {p.border};
    padding: 8px 6px;
}}
QScrollBar:vertical {{
    background: {p.surface_alt};
    width: 8px;
}}
QScrollBar::handle:vertical {{
    background: {p.border_strong};
    border-radius: 4px;
}}
"""


def algo_colors(p: Palette) -> dict:
    return {
        "Leaky Bucket": p.accent,
        "Token Bucket": p.purple,
        "RED": p.warning,
        "CoDel": p.success,
    }


def isp_verdict_display(p: Palette) -> dict:
    return {
        "healthy": ("Healthy", p.success),
        "local_congestion": ("Local Congestion", p.warning),
        "last_mile": ("Last Mile Issue", p.danger),
        "isp_degradation": ("ISP Degradation", p.warning),
        "isp_outage": ("ISP Outage", p.danger),
        "dns_issue": ("DNS Issue", p.danger),
    }


def _fmt_time(ts: float) -> str:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return "—"


def _segment_button(label: str) -> QPushButton:
    btn = QPushButton(label)
    btn.setCheckable(True)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setFixedHeight(34)
    style(btn, lambda p: f"""
        QPushButton {{
            background-color: {p.surface};
            color: {p.text_secondary};
            border: 1px solid {p.border_strong};
            border-radius: 8px;
            padding: 6px 16px;
            font-size: 12px;
            font-weight: 700;
        }}
        QPushButton:hover {{ border-color: {p.accent}; color: {p.accent}; }}
        QPushButton:checked {{
            background-color: {p.selection};
            color: {p.accent};
            border-color: {p.accent};
        }}
    """)
    return btn


def _empty_state(text: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(24, 40, 24, 40)
    lbl = QLabel(text)
    style(lbl, lambda p: f"font-size: 13px; color: {p.text_muted};")
    lbl.setWordWrap(True)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(lbl)
    return frame


class HistoryView(QWidget):
    def __init__(self):
        super().__init__()
        self._diag_rows: list[dict] = []
        self._sim_rows: list[dict] = []
        self._policy_rows: list[dict] = []

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        style(scroll, lambda p: f"QScrollArea {{ background: {p.bg}; border: none; }}")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("History")
        style(title, lambda p: f"font-size: 26px; font-weight: 800; color: {p.text_strong};")
        subtitle = QLabel("Past diagnostics, simulation runs, and applied fixes")
        style(subtitle, lambda p: f"font-size: 13px; color: {p.text_muted};")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        self._btn_export = QPushButton("Export CSV")
        self._btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_export.setFixedHeight(36)
        self._btn_export.clicked.connect(self._export_current_tab)
        header.addWidget(self._btn_export)

        layout.addLayout(header)

        # Segmented tab control
        tabs_row = QHBoxLayout()
        tabs_row.setSpacing(8)
        self._btn_diag_tab = _segment_button("Diagnostics")
        self._btn_sim_tab = _segment_button("Simulations")
        self._btn_fix_tab = _segment_button("Applied Fixes")
        self._btn_diag_tab.setChecked(True)
        tabs_row.addWidget(self._btn_diag_tab)
        tabs_row.addWidget(self._btn_sim_tab)
        tabs_row.addWidget(self._btn_fix_tab)
        tabs_row.addStretch()
        layout.addLayout(tabs_row)

        self._btn_diag_tab.clicked.connect(lambda: self._switch_tab(0))
        self._btn_sim_tab.clicked.connect(lambda: self._switch_tab(1))
        self._btn_fix_tab.clicked.connect(lambda: self._switch_tab(2))

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # --- Diagnostics tab: master/detail ---
        diag_page = QWidget()
        diag_layout = QHBoxLayout(diag_page)
        diag_layout.setContentsMargins(0, 0, 0, 0)
        diag_layout.setSpacing(14)

        self._diag_table = QTableWidget(0, 5)
        style(self._diag_table, table_style)
        self._diag_table.setHorizontalHeaderLabels(["Time", "Score", "Severity", "ISP Verdict", "Recommended"])
        self._diag_table.verticalHeader().hide()
        self._diag_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._diag_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._diag_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._diag_table.itemSelectionChanged.connect(self._on_diag_selected)
        diag_layout.addWidget(self._diag_table, 3)

        self._diag_detail = QFrame()
        self._diag_detail.setObjectName("card")
        self._diag_detail.setMinimumWidth(280)
        dd = QVBoxLayout(self._diag_detail)
        dd.setContentsMargins(18, 16, 18, 16)
        dd.setSpacing(8)
        dd_title = QLabel("RUN DETAIL")
        style(dd_title, lambda p: f"font-size: 11px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")
        dd.addWidget(dd_title)
        self._diag_detail_algo = QLabel("Select a row")
        style(self._diag_detail_algo, lambda p: f"font-size: 18px; font-weight: 800; color: {p.accent};")
        dd.addWidget(self._diag_detail_algo)
        self._diag_detail_reason = QLabel("")
        style(self._diag_detail_reason, lambda p: f"font-size: 12px; color: {p.text_secondary};")
        self._diag_detail_reason.setWordWrap(True)
        dd.addWidget(self._diag_detail_reason)
        self._diag_detail_meta = QLabel("")
        style(self._diag_detail_meta, lambda p: f"font-size: 11px; color: {p.text_faint};")
        self._diag_detail_meta.setWordWrap(True)
        dd.addWidget(self._diag_detail_meta)
        dd.addStretch()
        diag_layout.addWidget(self._diag_detail, 2)

        self._stack.addWidget(diag_page)

        # --- Simulations tab: master/detail ---
        sim_page = QWidget()
        sim_layout = QHBoxLayout(sim_page)
        sim_layout.setContentsMargins(0, 0, 0, 0)
        sim_layout.setSpacing(14)

        self._sim_table = QTableWidget(0, 6)
        style(self._sim_table, table_style)
        self._sim_table.setHorizontalHeaderLabels(
            ["Time", "Scenario", "Algorithm", "Throughput", "Latency", "Loss"])
        self._sim_table.verticalHeader().hide()
        self._sim_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._sim_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._sim_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._sim_table.itemSelectionChanged.connect(self._on_sim_selected)
        sim_layout.addWidget(self._sim_table, 3)

        self._sim_detail = QFrame()
        self._sim_detail.setObjectName("card")
        self._sim_detail.setMinimumWidth(280)
        sd = QVBoxLayout(self._sim_detail)
        sd.setContentsMargins(18, 16, 18, 16)
        sd.setSpacing(8)
        sd_title = QLabel("RUN DETAIL")
        style(sd_title, lambda p: f"font-size: 11px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")
        sd.addWidget(sd_title)
        self._sim_detail_algo = QLabel("Select a row")
        style(self._sim_detail_algo, lambda p: f"font-size: 18px; font-weight: 800; color: {p.purple};")
        sd.addWidget(self._sim_detail_algo)
        self._sim_detail_metrics = QLabel("")
        style(self._sim_detail_metrics, lambda p: f"font-size: 12px; color: {p.text_secondary};")
        self._sim_detail_metrics.setWordWrap(True)
        sd.addWidget(self._sim_detail_metrics)
        self._sim_detail_params = QLabel("")
        style(self._sim_detail_params, lambda p: f"font-size: 11px; color: {p.text_faint};")
        self._sim_detail_params.setWordWrap(True)
        sd.addWidget(self._sim_detail_params)
        sd.addStretch()
        sim_layout.addWidget(self._sim_detail, 2)

        self._stack.addWidget(sim_page)

        # --- Applied Fixes tab ---
        fix_page = QWidget()
        fix_layout = QVBoxLayout(fix_page)
        fix_layout.setContentsMargins(0, 0, 0, 0)
        fix_layout.setSpacing(10)

        self._fix_table = QTableWidget(0, 6)
        style(self._fix_table, table_style)
        self._fix_table.setHorizontalHeaderLabels(
            ["Time", "Interface", "Algorithm", "Score Before", "Score After", "Rolled Back"])
        self._fix_table.verticalHeader().hide()
        self._fix_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._fix_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._fix_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        fix_layout.addWidget(self._fix_table)

        self._fix_empty = _empty_state(
            "No fixes have been applied yet.\n\n"
            "Once Real Network Mode enforces a supported congestion-management policy with your "
            "approval, each applied fix and its before/after verification will appear here."
        )
        fix_layout.addWidget(self._fix_empty)

        self._stack.addWidget(fix_page)

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

        theme_manager.changed.connect(self._on_theme_changed)
        self._load_all()

    def showEvent(self, event):
        super().showEvent(event)
        self._load_all()

    def _on_theme_changed(self, _name: str):
        self._populate_diag_table()
        self._populate_sim_table()
        self._populate_fix_table()
        self._on_diag_selected()
        self._on_sim_selected()

    def _switch_tab(self, index: int):
        for i, btn in enumerate((self._btn_diag_tab, self._btn_sim_tab, self._btn_fix_tab)):
            btn.setChecked(i == index)
        self._stack.setCurrentIndex(index)

    # --- Data loading ---
    def _load_all(self):
        try:
            conn = get_connection()
            init_db(conn)
            repo = Repository(conn)
            self._diag_rows = repo.get_diagnostic_runs(limit=200)
            self._sim_rows = repo.get_simulation_results(limit=200)
            self._policy_rows = repo.get_applied_policies(limit=200)
            conn.close()
        except Exception:
            self._diag_rows, self._sim_rows, self._policy_rows = [], [], []

        self._populate_diag_table()
        self._populate_sim_table()
        self._populate_fix_table()

    def _populate_diag_table(self):
        p = theme_manager.palette
        isp_display = isp_verdict_display(p)

        self._diag_table.setRowCount(len(self._diag_rows))
        for row, r in enumerate(self._diag_rows):
            self._diag_table.setItem(row, 0, QTableWidgetItem(_fmt_time(r["timestamp"])))
            self._diag_table.setItem(row, 1, QTableWidgetItem(f"{r['congestion_score'] or 0:.0f}"))
            self._diag_table.setItem(row, 2, QTableWidgetItem(r["severity"] or "—"))
            verdict_text, _ = isp_display.get(r["isp_verdict"] or "", (r["isp_verdict"] or "—", p.text_secondary))
            self._diag_table.setItem(row, 3, QTableWidgetItem(verdict_text))
            algo_item = QTableWidgetItem(r["recommended_algo"] or "None needed")
            self._diag_table.setItem(row, 4, algo_item)
        if self._diag_rows:
            self._diag_table.selectRow(0)

    def _populate_sim_table(self):
        self._sim_table.setRowCount(len(self._sim_rows))
        for row, r in enumerate(self._sim_rows):
            self._sim_table.setItem(row, 0, QTableWidgetItem(_fmt_time(r["timestamp"])))
            self._sim_table.setItem(row, 1, QTableWidgetItem((r["scenario"] or "—").replace("_", " ").title()))
            self._sim_table.setItem(row, 2, QTableWidgetItem(r["algorithm"] or "—"))
            self._sim_table.setItem(row, 3, QTableWidgetItem(f"{r['throughput_mbps'] or 0:.2f} Mbps"))
            self._sim_table.setItem(row, 4, QTableWidgetItem(f"{r['avg_latency_ms'] or 0:.1f} ms"))
            self._sim_table.setItem(row, 5, QTableWidgetItem(f"{r['loss_pct'] or 0:.2f} %"))
        if self._sim_rows:
            self._sim_table.selectRow(0)

    def _populate_fix_table(self):
        has_data = bool(self._policy_rows)
        self._fix_table.setVisible(has_data)
        self._fix_empty.setVisible(not has_data)
        if not has_data:
            return
        self._fix_table.setRowCount(len(self._policy_rows))
        for row, r in enumerate(self._policy_rows):
            self._fix_table.setItem(row, 0, QTableWidgetItem(_fmt_time(r["timestamp"])))
            self._fix_table.setItem(row, 1, QTableWidgetItem(r["interface"] or "—"))
            self._fix_table.setItem(row, 2, QTableWidgetItem(r["algorithm"] or "—"))
            self._fix_table.setItem(row, 3, QTableWidgetItem(f"{r['score_before'] or 0:.0f}"))
            after = r["score_after"]
            self._fix_table.setItem(row, 4, QTableWidgetItem(f"{after:.0f}" if after is not None else "—"))
            self._fix_table.setItem(row, 5, QTableWidgetItem("Yes" if r["rolled_back_at"] else "No"))

    # --- Detail panels ---
    def _on_diag_selected(self):
        rows = self._diag_table.selectionModel().selectedRows()
        if not rows or not self._diag_rows:
            return
        p = theme_manager.palette
        algo_c = algo_colors(p)

        r = self._diag_rows[rows[0].row()]
        algo = r["recommended_algo"] or "No algorithm needed"
        color = algo_c.get(algo, p.success)
        self._diag_detail_algo.setText(algo)
        self._diag_detail_algo.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {color};")
        self._diag_detail_reason.setText(r["recommendation_reason"] or "No reason recorded.")
        self._diag_detail_meta.setText(
            f"Dominant signal: {(r['dominant_signal'] or '—').replace('_', ' ')}\n"
            f"Confidence: {r['confidence'] or '—'}\n"
            f"Session: {r['session_id'][:8] if r['session_id'] else '—'}…\n"
            f"Run at: {_fmt_time(r['timestamp'])}"
        )

    def _on_sim_selected(self):
        rows = self._sim_table.selectionModel().selectedRows()
        if not rows or not self._sim_rows:
            return
        p = theme_manager.palette
        algo_c = algo_colors(p)

        r = self._sim_rows[rows[0].row()]
        color = algo_c.get(r["algorithm"], p.purple)
        self._sim_detail_algo.setText(r["algorithm"] or "—")
        self._sim_detail_algo.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {color};")
        self._sim_detail_metrics.setText(
            f"Throughput: {r['throughput_mbps'] or 0:.2f} Mbps\n"
            f"Avg latency: {r['avg_latency_ms'] or 0:.1f} ms\n"
            f"Loss: {r['loss_pct'] or 0:.2f} %\n"
            f"Fairness index: {r['fairness_index'] or 0:.3f}\n"
            f"Engine: {r['engine_used'] or '—'}"
        )
        try:
            params = json.loads(r["parameters"] or "{}")
            detail = json.loads(r["metrics_detail"] or "{}")
            self._sim_detail_params.setText(
                "Parameters: " + ", ".join(f"{k}={v}" for k, v in params.items()) + "\n"
                "Extra: " + ", ".join(f"{k}={v}" for k, v in detail.items())
            )
        except Exception:
            self._sim_detail_params.setText("")

    # --- Export ---
    def _export_current_tab(self):
        idx = self._stack.currentIndex()
        if idx == 0 and self._diag_rows:
            rows, name = self._diag_rows, "diagnostics_history"
        elif idx == 1 and self._sim_rows:
            rows, name = self._sim_rows, "simulation_history"
        elif idx == 2 and self._policy_rows:
            rows, name = self._policy_rows, "applied_fixes_history"
        else:
            return

        default_name = str(default_export_dir() / f"{name}_{int(time.time())}.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export History", default_name, "CSV Files (*.csv)")
        if not path:
            return
        try:
            export_rows_to_csv(rows, path)
        except Exception:
            pass