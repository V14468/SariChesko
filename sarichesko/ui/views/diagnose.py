import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QProgressBar, QGraphicsOpacityEffect, QScrollArea,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve

from ..widgets.congestion_gauge import CongestionGaugeWidget
from ..widgets.isp_status_panel import ISPStatusPanel
from ...platform import get_monitor
from ...core.diagnostics_engine import DiagnosticsWorker, DiagnosticResult
from ...core.recommendation_engine import Algorithm


ALGO_COLORS = {
    Algorithm.LEAKY_BUCKET: "#00f0ff",
    Algorithm.TOKEN_BUCKET: "#a78bfa",
    Algorithm.RED: "#f59e0b",
    Algorithm.CODEL: "#00e5a3",
}


class DiagnoseView(QWidget):
    def __init__(self):
        super().__init__()
        self._worker: DiagnosticsWorker = None
        self._monitor = get_monitor()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #000000; border: none; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(20)

        # Header
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title = QLabel("Network Diagnostics")
        title.setStyleSheet("font-size: 26px; font-weight: 800; color: #ffffff;")
        subtitle = QLabel("Full diagnostic: ISP probe, congestion scoring, algorithm recommendation")
        subtitle.setStyleSheet("font-size: 13px; color: #64748b;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        self._iface_combo = QComboBox()
        self._iface_combo.setFixedWidth(220)
        self._iface_combo.setFixedHeight(36)
        header.addWidget(self._iface_combo)

        self._btn_run = QPushButton("Run Full Diagnostic")
        self._btn_run.setObjectName("primary_btn")
        self._btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_run.setFixedHeight(36)
        self._btn_run.clicked.connect(self._run_diagnostic)
        header.addWidget(self._btn_run)

        layout.addLayout(header)

        # Populate interfaces
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

        # Progress section
        self._progress_frame = QFrame()
        self._progress_frame.setObjectName("card")
        prog_layout = QVBoxLayout(self._progress_frame)
        prog_layout.setContentsMargins(20, 16, 20, 16)
        prog_layout.setSpacing(8)

        self._progress_label = QLabel("Ready to run diagnostic")
        self._progress_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #94a3b8;")
        prog_layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet("""
            QProgressBar { background-color: #121420; border: none; border-radius: 3px; }
            QProgressBar::chunk { background-color: #00f0ff; border-radius: 3px; }
        """)
        self._progress_bar.setValue(0)
        prog_layout.addWidget(self._progress_bar)

        layout.addWidget(self._progress_frame)

        # Results area (hidden initially)
        self._results_widget = QWidget()
        self._results_widget.setVisible(False)
        results_layout = QVBoxLayout(self._results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(16)

        # Row 1: Congestion Score + ISP Status
        row1 = QHBoxLayout()
        row1.setSpacing(14)

        gauge_card = QFrame()
        gauge_card.setObjectName("card")
        gauge_layout = QVBoxLayout(gauge_card)
        gauge_layout.setContentsMargins(20, 16, 20, 16)

        gauge_title = QLabel("CONGESTION SCORE")
        gauge_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        gauge_layout.addWidget(gauge_title)

        self._gauge = CongestionGaugeWidget()
        self._gauge.setMinimumSize(200, 200)
        gauge_layout.addWidget(self._gauge)

        row1.addWidget(gauge_card)

        isp_card = QFrame()
        isp_card.setObjectName("card")
        isp_layout = QVBoxLayout(isp_card)
        isp_layout.setContentsMargins(20, 16, 20, 16)

        self._isp_panel = ISPStatusPanel()
        isp_layout.addWidget(self._isp_panel)

        row1.addWidget(isp_card)
        results_layout.addLayout(row1)

        # Row 2: Recommendation
        self._rec_card = QFrame()
        self._rec_card.setObjectName("card")
        rec_layout = QVBoxLayout(self._rec_card)
        rec_layout.setContentsMargins(24, 20, 24, 20)
        rec_layout.setSpacing(12)

        rec_header = QHBoxLayout()
        rec_title = QLabel("RECOMMENDATION")
        rec_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        rec_header.addWidget(rec_title)
        rec_header.addStretch()

        self._confidence_label = QLabel("")
        self._confidence_label.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b;")
        rec_header.addWidget(self._confidence_label)
        rec_layout.addLayout(rec_header)

        self._algo_label = QLabel("—")
        self._algo_label.setStyleSheet("font-size: 28px; font-weight: 800; color: #00f0ff;")
        rec_layout.addWidget(self._algo_label)

        self._reason_label = QLabel("")
        self._reason_label.setStyleSheet("font-size: 13px; color: #e2e8f0; line-height: 1.5;")
        self._reason_label.setWordWrap(True)
        rec_layout.addWidget(self._reason_label)

        self._actions_label = QLabel("")
        self._actions_label.setStyleSheet("font-size: 12px; color: #94a3b8;")
        self._actions_label.setWordWrap(True)
        rec_layout.addWidget(self._actions_label)

        results_layout.addWidget(self._rec_card)

        # Row 3: Measurement Summary
        self._summary_card = QFrame()
        self._summary_card.setObjectName("card")
        sum_layout = QVBoxLayout(self._summary_card)
        sum_layout.setContentsMargins(20, 16, 20, 16)
        sum_layout.setSpacing(8)

        sum_title = QLabel("MEASUREMENT SUMMARY")
        sum_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        sum_layout.addWidget(sum_title)

        self._stats_grid = QHBoxLayout()
        self._stats_grid.setSpacing(16)
        self._stat_values = {}

        for key, label_text, unit, color in [
            ("latency", "Avg Latency", "ms", "#00f0ff"),
            ("loss", "Avg Loss", "%", "#ef4444"),
            ("bandwidth", "Avg Bandwidth", "Mbps", "#a78bfa"),
            ("jitter", "Avg Jitter", "ms", "#f59e0b"),
        ]:
            col = QVBoxLayout()
            col.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #64748b;")
            val = QLabel("—")
            val.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {color};")
            unit_lbl = QLabel(unit)
            unit_lbl.setStyleSheet(f"font-size: 11px; color: {color};")
            col.addWidget(lbl)
            col.addWidget(val)
            col.addWidget(unit_lbl)
            self._stats_grid.addLayout(col)
            self._stat_values[key] = val

        sum_layout.addLayout(self._stats_grid)
        results_layout.addWidget(self._summary_card)

        layout.addWidget(self._results_widget)
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

    def _run_diagnostic(self):
        iface = self._iface_combo.currentData()
        if not iface:
            return

        self._btn_run.setEnabled(False)
        self._btn_run.setText("Running...")
        self._results_widget.setVisible(False)
        self._progress_bar.setValue(0)
        self._progress_label.setText("Starting diagnostic...")
        self._progress_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #94a3b8;")

        self._worker = DiagnosticsWorker(iface)
        self._worker.progress.connect(self._on_progress)
        self._worker.complete.connect(self._on_complete)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_progress(self, text: str, value: int):
        self._progress_label.setText(text)
        self._progress_bar.setValue(value)

    def _on_complete(self, result: DiagnosticResult):
        self._btn_run.setEnabled(True)
        self._btn_run.setText("Run Full Diagnostic")
        self._progress_label.setText("Diagnostic complete!")
        self._progress_bar.setValue(100)

        # Congestion gauge
        self._gauge.set_score(result.congestion_score.score, result.congestion_score.severity)

        # ISP panel
        self._isp_panel.update_result(result.isp_result)

        # Recommendation
        rec = result.recommendation
        if rec.algo:
            color = ALGO_COLORS.get(rec.algo, "#00f0ff")
            self._algo_label.setText(rec.algo.value)
            self._algo_label.setStyleSheet(f"font-size: 28px; font-weight: 800; color: {color};")
        else:
            self._algo_label.setText("No Algorithm Needed")
            self._algo_label.setStyleSheet("font-size: 28px; font-weight: 800; color: #00e5a3;")

        conf_colors = {"HIGH": "#00e5a3", "MEDIUM": "#f59e0b", "LOW": "#ef4444"}
        self._confidence_label.setText(f"Confidence: {rec.confidence}")
        self._confidence_label.setStyleSheet(
            f"font-size: 11px; font-weight: 700; color: {conf_colors.get(rec.confidence, '#64748b')};"
        )

        self._reason_label.setText(rec.reason)
        self._actions_label.setText("Actions: " + " → ".join(rec.actions))

        # Measurement averages
        ms = result.measurements
        if ms:
            self._stat_values["latency"].setText(f"{sum(m.latency_ms for m in ms)/len(ms):.1f}")
            self._stat_values["loss"].setText(f"{sum(m.packet_loss_pct for m in ms)/len(ms):.2f}")
            self._stat_values["bandwidth"].setText(f"{sum(m.bandwidth_mbps for m in ms)/len(ms):.2f}")
            self._stat_values["jitter"].setText(f"{sum(m.jitter_ms for m in ms)/len(ms):.1f}")

        self._results_widget.setVisible(True)
        self._worker = None

    def _on_error(self, msg: str):
        self._btn_run.setEnabled(True)
        self._btn_run.setText("Run Full Diagnostic")
        self._progress_label.setText(f"Error: {msg}")
        self._progress_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #ef4444;")
        self._worker = None