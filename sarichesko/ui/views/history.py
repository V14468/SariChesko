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


TABLE_STYLE = """
QTableWidget {
    background-color: #05060a;
    color: #e2e8f0;
    border: none;
    gridline-color: #121524;
    font-size: 12px;
    selection-background-color: #0c1424;
    selection-color: #00f0ff;
}
QTableWidget::item {
    padding: 6px;
    border-bottom: 1px solid #121524;
}
QHeaderView::section {
    background-color: #05060a;
    color: #64748b;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    border: none;
    border-bottom: 1px solid #121524;
    padding: 8px 6px;
}
QScrollBar:vertical {
    background: #05060a;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #1a1d2e;
    border-radius: 4px;
}
"""

ALGO_COLORS = {
    "Leaky Bucket": "#00f0ff",
    "Token Bucket": "#a78bfa",
    "RED": "#f59e0b",
    "CoDel": "#00e5a3",
}

ISP_VERDICT_DISPLAY = {
    "healthy": ("Healthy", "#00e5a3"),
    "local_congestion": ("Local Congestion", "#f59e0b"),
    "last_mile": ("Last Mile Issue", "#ef4444"),
    "isp_degradation": ("ISP Degradation", "#f59e0b"),
    "isp_outage": ("ISP Outage", "#ef4444"),
    "dns_issue": ("DNS Issue", "#ef4444"),
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
    btn.setStyleSheet("""
        QPushButton {
            background-color: #080a10;
            color: #94a3b8;
            border: 1px solid #1a1d2e;
            border-radius: 8px;
            padding: 6px 16px;
            font-size: 12px;
            font-weight: 700;
        }
        QPushButton:hover { border-color: #00f0ff; color: #00f0ff; }
        QPushButton:checked {
            background-color: #0c1424;
            color: #00f0ff;
            border-color: #00f0ff;
        }
    """)
    return btn


def _empty_state(text: str) -> QFrame:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(24, 40, 24, 40)
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size: 13px; color: #64748b;")
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
        scroll.setStyleSheet("QScrollArea { background: #000000; border: none; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("History")
        title.setStyleSheet("font-size: 26px; font-weight: 800; color: #ffffff;")
        subtitle = QLabel("Past diagnostics, simulation runs, and applied fixes")
        subtitle.setStyleSheet("font-size: 13px; color: #64748b;")
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
        self._diag_table.setStyleSheet(TABLE_STYLE)
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
        dd_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        dd.addWidget(dd_title)
        self._diag_detail_algo = QLabel("Select a row")
        self._diag_detail_algo.setStyleSheet("font-size: 18px; font-weight: 800; color: #00f0ff;")
        dd.addWidget(self._diag_detail_algo)
        self._diag_detail_reason = QLabel("")
        self._diag_detail_reason.setStyleSheet("font-size: 12px; color: #94a3b8;")
        self._diag_detail_reason.setWordWrap(True)
        dd.addWidget(self._diag_detail_reason)
        self._diag_detail_meta = QLabel("")
        self._diag_detail_meta.setStyleSheet("font-size: 11px; color: #475569;")
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
        self._sim_table.setStyleSheet(TABLE_STYLE)
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
        sd_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        sd.addWidget(sd_title)
        self._sim_detail_algo = QLabel("Select a row")
        self._sim_detail_algo.setStyleSheet("font-size: 18px; font-weight: 800; color: #a78bfa;")
        sd.addWidget(self._sim_detail_algo)
        self._sim_detail_metrics = QLabel("")
        self._sim_detail_metrics.setStyleSheet("font-size: 12px; color: #94a3b8;")
        self._sim_detail_metrics.setWordWrap(True)
        sd.addWidget(self._sim_detail_metrics)
        self._sim_detail_params = QLabel("")
        self._sim_detail_params.setStyleSheet("font-size: 11px; color: #475569;")
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
        self._fix_table.setStyleSheet(TABLE_STYLE)
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

        self._load_all()

    def showEvent(self, event):
        super().showEvent(event)
        self._load_all()

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
        self._diag_table.setRowCount(len(self._diag_rows))
        for row, r in enumerate(self._diag_rows):
            self._diag_table.setItem(row, 0, QTableWidgetItem(_fmt_time(r["timestamp"])))
            self._diag_table.setItem(row, 1, QTableWidgetItem(f"{r['congestion_score'] or 0:.0f}"))
            self._diag_table.setItem(row, 2, QTableWidgetItem(r["severity"] or "—"))
            verdict_text, _ = ISP_VERDICT_DISPLAY.get(r["isp_verdict"] or "", (r["isp_verdict"] or "—", "#94a3b8"))
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
        r = self._diag_rows[rows[0].row()]
        algo = r["recommended_algo"] or "No algorithm needed"
        color = ALGO_COLORS.get(algo, "#00e5a3")
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
        r = self._sim_rows[rows[0].row()]
        color = ALGO_COLORS.get(r["algorithm"], "#a78bfa")
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