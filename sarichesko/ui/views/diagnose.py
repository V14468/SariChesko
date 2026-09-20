from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QProgressBar, QGraphicsOpacityEffect, QScrollArea,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve

from ..widgets.congestion_gauge import CongestionGaugeWidget
from ..widgets.isp_status_panel import ISPStatusPanel
from ..widgets.permission_dialog import PermissionDialog
from ..widgets.rollback_dialog import RollbackDialog
from ...platform import get_monitor, get_controller
from ...core.diagnostics_engine import DiagnosticsWorker, DiagnosticResult
from ...core.recommendation_engine import Algorithm
from ...core.traffic_control_manager import ApplyFixWorker, RollbackWorker


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
        self._apply_worker: ApplyFixWorker = None
        self._rollback_worker: RollbackWorker = None
        self._monitor = get_monitor()
        self._controller = get_controller()
        self._current_result: DiagnosticResult = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 16)
        layout.setSpacing(12)

        # Header row
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        title = QLabel("Network Diagnostics")
        title.setStyleSheet("font-size: 24px; font-weight: 800; color: #ffffff;")
        subtitle = QLabel("ISP probe · Congestion scoring · Algorithm recommendation")
        subtitle.setStyleSheet("font-size: 12px; color: #64748b;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        self._iface_combo = QComboBox()
        self._iface_combo.setFixedWidth(200)
        self._iface_combo.setFixedHeight(34)
        header.addWidget(self._iface_combo)

        self._btn_run = QPushButton("Run Full Diagnostic")
        self._btn_run.setObjectName("primary_btn")
        self._btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_run.setFixedHeight(34)
        self._btn_run.clicked.connect(self._run_diagnostic)
        header.addWidget(self._btn_run)

        layout.addLayout(header)

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

        # Progress bar (compact)
        self._progress_label = QLabel("Ready to run diagnostic")
        self._progress_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #94a3b8;")
        layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet("""
            QProgressBar { background-color: #121420; border: none; border-radius: 2px; }
            QProgressBar::chunk { background-color: #00f0ff; border-radius: 2px; }
        """)
        self._progress_bar.setValue(0)
        layout.addWidget(self._progress_bar)

        # Results (hidden initially)
        self._results_widget = QWidget()
        self._results_widget.setVisible(False)
        results_layout = QVBoxLayout(self._results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(10)

        # Row 1: Gauge + ISP (side by side, compact)
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        gauge_card = QFrame()
        gauge_card.setObjectName("card")
        gauge_layout = QVBoxLayout(gauge_card)
        gauge_layout.setContentsMargins(14, 10, 14, 10)
        gauge_layout.setSpacing(4)

        gauge_title = QLabel("CONGESTION SCORE")
        gauge_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        gauge_layout.addWidget(gauge_title)

        self._gauge = CongestionGaugeWidget()
        self._gauge.setFixedSize(150, 150)
        gauge_layout.addWidget(self._gauge, 0, Qt.AlignmentFlag.AlignCenter)

        row1.addWidget(gauge_card)

        isp_card = QFrame()
        isp_card.setObjectName("card")
        isp_layout = QVBoxLayout(isp_card)
        isp_layout.setContentsMargins(14, 10, 14, 10)

        self._isp_panel = ISPStatusPanel()
        isp_layout.addWidget(self._isp_panel)

        row1.addWidget(isp_card, 1)
        results_layout.addLayout(row1)

        # Row 2: Recommendation (compact)
        self._rec_card = QFrame()
        self._rec_card.setObjectName("card")
        rec_layout = QHBoxLayout(self._rec_card)
        rec_layout.setContentsMargins(18, 14, 18, 14)
        rec_layout.setSpacing(16)

        rec_left = QVBoxLayout()
        rec_left.setSpacing(4)

        rec_header_row = QHBoxLayout()
        rec_title = QLabel("RECOMMENDATION")
        rec_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        rec_header_row.addWidget(rec_title)
        rec_header_row.addStretch()
        self._confidence_label = QLabel("")
        self._confidence_label.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b;")
        rec_header_row.addWidget(self._confidence_label)
        rec_left.addLayout(rec_header_row)

        self._algo_label = QLabel("—")
        self._algo_label.setStyleSheet("font-size: 22px; font-weight: 800; color: #00f0ff;")
        rec_left.addWidget(self._algo_label)

        self._reason_label = QLabel("")
        self._reason_label.setStyleSheet("font-size: 12px; color: #e2e8f0;")
        self._reason_label.setWordWrap(True)
        rec_left.addWidget(self._reason_label)

        self._actions_label = QLabel("")
        self._actions_label.setStyleSheet("font-size: 11px; color: #94a3b8;")
        self._actions_label.setWordWrap(True)
        rec_left.addWidget(self._actions_label)

        apply_row = QHBoxLayout()
        apply_row.setSpacing(10)
        self._btn_apply_fix = QPushButton("Apply Fix")
        self._btn_apply_fix.setObjectName("primary_btn")
        self._btn_apply_fix.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_apply_fix.setFixedHeight(32)
        self._btn_apply_fix.setVisible(False)
        self._btn_apply_fix.clicked.connect(self._on_apply_fix_clicked)
        apply_row.addWidget(self._btn_apply_fix)

        self._apply_status_label = QLabel("")
        self._apply_status_label.setStyleSheet("font-size: 11px; color: #94a3b8;")
        self._apply_status_label.setWordWrap(True)
        apply_row.addWidget(self._apply_status_label, 1)
        rec_left.addLayout(apply_row)

        rec_layout.addLayout(rec_left)
        results_layout.addWidget(self._rec_card)

        # Row 3: Measurement Summary (horizontal, compact)
        self._summary_card = QFrame()
        self._summary_card.setObjectName("card")
        sum_layout = QHBoxLayout(self._summary_card)
        sum_layout.setContentsMargins(18, 12, 18, 12)
        sum_layout.setSpacing(24)

        self._stat_values = {}
        for key, label_text, unit, color in [
            ("latency", "Avg Latency", "ms", "#00f0ff"),
            ("loss", "Avg Loss", "%", "#ef4444"),
            ("bandwidth", "Avg Bandwidth", "Mbps", "#a78bfa"),
            ("jitter", "Avg Jitter", "ms", "#f59e0b"),
        ]:
            col = QVBoxLayout()
            col.setSpacing(2)
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b;")

            val_row = QHBoxLayout()
            val_row.setSpacing(3)
            val = QLabel("—")
            val.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {color};")
            u_lbl = QLabel(unit)
            u_lbl.setStyleSheet(f"font-size: 11px; color: {color}; padding-top: 6px;")
            val_row.addWidget(val)
            val_row.addWidget(u_lbl)
            val_row.addStretch()

            col.addWidget(lbl)
            col.addLayout(val_row)
            sum_layout.addLayout(col)
            self._stat_values[key] = val

        results_layout.addWidget(self._summary_card)

        layout.addWidget(self._results_widget)
        layout.addStretch()

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
        self._progress_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #94a3b8;")

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
        self._current_result = result
        self._apply_status_label.setText("")

        self._gauge.set_score(result.congestion_score.score, result.congestion_score.severity)
        self._isp_panel.update_result(result.isp_result)

        rec = result.recommendation
        if rec.algo:
            color = ALGO_COLORS.get(rec.algo, "#00f0ff")
            self._algo_label.setText(rec.algo.value)
            self._algo_label.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {color};")
            self._btn_apply_fix.setVisible(True)
            self._btn_apply_fix.setEnabled(True)
            self._btn_apply_fix.setText(f"Apply {rec.algo.value}")
            if not self._controller.is_algorithm_supported(rec.algo.value):
                self._apply_status_label.setText(
                    f"{rec.algo.value} is simulate-only on this OS \u2014 clicking Apply will explain why."
                )
        else:
            self._algo_label.setText("No Algorithm Needed")
            self._algo_label.setStyleSheet("font-size: 22px; font-weight: 800; color: #00e5a3;")
            self._btn_apply_fix.setVisible(False)

        conf_colors = {"HIGH": "#00e5a3", "MEDIUM": "#f59e0b", "LOW": "#ef4444"}
        self._confidence_label.setText(f"Confidence: {rec.confidence}")
        self._confidence_label.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: {conf_colors.get(rec.confidence, '#64748b')};"
        )

        self._reason_label.setText(rec.reason)
        self._actions_label.setText("Actions: " + " → ".join(rec.actions))

        ms = result.measurements
        if ms:
            self._stat_values["latency"].setText(f"{sum(m.latency_ms for m in ms)/len(ms):.1f}")
            self._stat_values["loss"].setText(f"{sum(m.packet_loss_pct for m in ms)/len(ms):.2f}")
            self._stat_values["bandwidth"].setText(f"{sum(m.bandwidth_mbps for m in ms)/len(ms):.2f}")
            self._stat_values["jitter"].setText(f"{sum(m.jitter_ms for m in ms)/len(ms):.1f}")

        self._results_widget.setVisible(True)

    def _on_error(self, msg: str):
        self._btn_run.setEnabled(True)
        self._btn_run.setText("Run Full Diagnostic")
        self._progress_label.setText(f"Error: {msg}")
        self._progress_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #ef4444;")

    # --- Apply Fix (human-in-the-loop) ---
    def _on_apply_fix_clicked(self):
        if not self._current_result or not self._current_result.recommendation.algo:
            return
        rec = self._current_result.recommendation
        algo = rec.algo
        iface = self._iface_combo.currentData()
        if not iface:
            return

        supported = self._controller.is_algorithm_supported(algo.value)
        unsupported_message = ""
        if not supported:
            # These calls are side-effect-free when unsupported (the platform
            # controllers return a fixed explanatory ApplyResult immediately,
            # without touching the OS) -- safe to call just to get the exact
            # wording, so the dialog and the real apply path never disagree.
            p = rec.parameters
            if algo == Algorithm.LEAKY_BUCKET:
                unsupported_message = self._controller.apply_leaky_bucket(iface, p["rate_bps"], p["burst_bytes"]).message
            elif algo == Algorithm.TOKEN_BUCKET:
                unsupported_message = self._controller.apply_token_bucket(iface, p["rate_bps"], p["burst_bytes"], p["latency_ms"]).message
            elif algo == Algorithm.RED:
                unsupported_message = self._controller.apply_red(iface, p["min_th"], p["max_th"], p["max_p"], p["limit"]).message
            elif algo == Algorithm.CODEL:
                unsupported_message = self._controller.apply_codel(iface, p["target_ms"], p["interval_ms"], p["limit"]).message

        dialog = PermissionDialog(
            iface=iface,
            algo=algo,
            parameters=rec.parameters,
            reason=rec.reason,
            congestion_score=self._current_result.congestion_score.score,
            severity=self._current_result.congestion_score.severity,
            supported=supported,
            requires_elevation=self._controller.requires_elevation(),
            unsupported_message=unsupported_message,
            parent=self,
        )
        if dialog.exec() != dialog.DialogCode.Accepted or not supported:
            return

        ms = self._current_result.measurements
        latency_before = sum(m.latency_ms for m in ms) / len(ms) if ms else None
        loss_before = sum(m.packet_loss_pct for m in ms) / len(ms) if ms else None

        self._btn_apply_fix.setEnabled(False)
        self._apply_status_label.setText("Applying fix...")
        self._apply_status_label.setStyleSheet("font-size: 11px; color: #94a3b8;")

        self._apply_worker = ApplyFixWorker(
            iface=iface,
            algo=algo,
            parameters=rec.parameters,
            score_before=self._current_result.congestion_score.score,
            diagnostic_id=self._current_result.id,
            latency_before_ms=latency_before,
            loss_before_pct=loss_before,
        )
        self._apply_worker.progress.connect(self._on_apply_progress)
        self._apply_worker.complete.connect(self._on_apply_complete)
        self._apply_worker.error.connect(self._on_apply_error)
        self._apply_worker.finished.connect(self._apply_worker.deleteLater)
        self._apply_worker.start()

    def _on_apply_progress(self, text: str, value: int):
        self._apply_status_label.setText(text)

    def _on_apply_complete(self, report):
        self._btn_apply_fix.setEnabled(True)

        if not report.applied:
            self._apply_status_label.setText(f"Not applied: {report.apply_message}")
            self._apply_status_label.setStyleSheet("font-size: 11px; color: #ef4444;")
            return

        self._apply_status_label.setText(report.apply_message)
        self._apply_status_label.setStyleSheet("font-size: 11px; color: #00e5a3;")

        algo_name = self._current_result.recommendation.algo.value if self._current_result.recommendation.algo else "Fix"
        dialog = RollbackDialog(
            algo_name=algo_name,
            score_before=report.score_before,
            score_after=report.score_after,
            verdict=report.verdict,
            latency_before=report.latency_before_ms,
            latency_after=report.latency_after_ms,
            loss_before=report.loss_before_pct,
            loss_after=report.loss_after_pct,
            apply_message=report.apply_message,
            parent=self,
        )
        dialog.exec()

        if dialog.rollback_requested and report.policy_id and report.snapshot:
            self._apply_status_label.setText("Rolling back...")
            self._apply_status_label.setStyleSheet("font-size: 11px; color: #94a3b8;")
            self._rollback_worker = RollbackWorker(report.policy_id, report.snapshot)
            self._rollback_worker.complete.connect(self._on_rollback_complete)
            self._rollback_worker.error.connect(self._on_apply_error)
            self._rollback_worker.finished.connect(self._rollback_worker.deleteLater)
            self._rollback_worker.start()

    def _on_rollback_complete(self, result):
        if result.success:
            self._apply_status_label.setText("Rolled back: " + result.message)
            self._apply_status_label.setStyleSheet("font-size: 11px; color: #94a3b8;")
        else:
            self._apply_status_label.setText("Rollback failed: " + result.message)
            self._apply_status_label.setStyleSheet("font-size: 11px; color: #ef4444;")

    def _on_apply_error(self, msg: str):
        self._btn_apply_fix.setEnabled(True)
        self._apply_status_label.setText(f"Error: {msg}")
        self._apply_status_label.setStyleSheet("font-size: 11px; color: #ef4444;")