import time
import uuid
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve

from ..widgets.latency_chart import LatencyChartWidget
from ..widgets.congestion_gauge import CongestionGaugeWidget
from ...platform import get_monitor
from ...core.monitor_engine import MonitorEngine
from ...core.congestion_scorer import score_congestion, CongestionScore
from ...storage.models import Measurement
from ...storage.db import get_connection, init_db
from ...storage.repository import Repository


class LiveNetworkView(QWidget):
    def __init__(self):
        super().__init__()
        self._engine: MonitorEngine = None
        self._session_id: str = None
        self._recent_scores: list[float] = []
        self._monitor = get_monitor()
        self._conn = get_connection()
        init_db(self._conn)
        self._repo = Repository(self._conn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        # Header
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title = QLabel("Live Network Monitor")
        title.setStyleSheet("font-size: 26px; font-weight: 800; color: #ffffff;")
        subtitle = QLabel("Real-time interface telemetry and congestion detection")
        subtitle.setStyleSheet("font-size: 13px; color: #64748b;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        self._iface_combo = QComboBox()
        self._iface_combo.setFixedWidth(220)
        self._iface_combo.setFixedHeight(36)
        header.addWidget(self._iface_combo)

        self._btn_start = QPushButton("Start Monitoring")
        self._btn_start.setObjectName("primary_btn")
        self._btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_start.setFixedHeight(36)
        self._btn_start.clicked.connect(self._toggle_monitoring)
        header.addWidget(self._btn_start)

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

        # Charts row
        charts_row = QHBoxLayout()
        charts_row.setSpacing(14)

        self._lat_chart = LatencyChartWidget("Latency", "ms", "#00f0ff")
        self._loss_chart = LatencyChartWidget("Packet Loss", "%", "#ef4444")
        charts_row.addWidget(self._lat_chart)
        charts_row.addWidget(self._loss_chart)
        layout.addLayout(charts_row)

        charts_row_2 = QHBoxLayout()
        charts_row_2.setSpacing(14)

        self._bw_chart = LatencyChartWidget("Bandwidth", "Mbps", "#a78bfa")
        self._jitter_chart = LatencyChartWidget("Jitter", "ms", "#f59e0b")
        charts_row_2.addWidget(self._bw_chart)
        charts_row_2.addWidget(self._jitter_chart)
        layout.addLayout(charts_row_2)

        # Bottom row: Gauge + Live Stats
        bottom = QHBoxLayout()
        bottom.setSpacing(14)

        gauge_card = QFrame()
        gauge_card.setObjectName("card")
        gauge_layout = QVBoxLayout(gauge_card)
        gauge_layout.setContentsMargins(16, 12, 16, 12)

        gauge_title = QLabel("CONGESTION SCORE")
        gauge_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        gauge_layout.addWidget(gauge_title)

        self._gauge = CongestionGaugeWidget()
        gauge_layout.addWidget(self._gauge)

        bottom.addWidget(gauge_card)

        stats_card = QFrame()
        stats_card.setObjectName("card")
        stats_layout = QVBoxLayout(stats_card)
        stats_layout.setContentsMargins(20, 16, 20, 16)
        stats_layout.setSpacing(12)

        stats_title = QLabel("LIVE STATS")
        stats_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        stats_layout.addWidget(stats_title)

        self._stat_labels = {}
        for key, label_text in [("latency", "Latency"), ("loss", "Packet Loss"),
                                 ("bandwidth", "Bandwidth"), ("jitter", "Jitter"),
                                 ("trend", "Trend"), ("dominant", "Dominant Signal")]:
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #94a3b8;")
            val = QLabel("—")
            val.setStyleSheet("font-size: 13px; font-weight: 700; color: #ffffff;")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            stats_layout.addLayout(row)
            self._stat_labels[key] = val

        stats_layout.addStretch()
        bottom.addWidget(stats_card)

        layout.addLayout(bottom)

        # Fade in
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._anim = QPropertyAnimation(self._opacity, b"opacity")
        self._anim.setDuration(350)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def _toggle_monitoring(self):
        if self._engine and self._engine.isRunning():
            self._engine.stop()
            self._engine.wait(3000)
            self._engine = None
            self._btn_start.setText("Start Monitoring")
            self._btn_start.setStyleSheet("")
            self._btn_start.setObjectName("primary_btn")
            self._btn_start.style().unpolish(self._btn_start)
            self._btn_start.style().polish(self._btn_start)
            return

        iface = self._iface_combo.currentData()
        if not iface:
            return

        self._session_id = str(uuid.uuid4())
        self._recent_scores = []

        from ...storage.models import Session
        self._repo.save_session(Session(
            id=self._session_id, started_at=time.time(), mode="real", interface=iface,
        ))

        baseline = self._repo.get_baseline(iface)

        self._engine = MonitorEngine(iface, self._session_id, interval_s=1.0)
        if baseline:
            self._engine.set_baseline(baseline)
        self._engine.measurement_ready.connect(self._on_measurement)
        self._engine.baseline_established.connect(self._on_baseline)
        self._engine.start()

        self._btn_start.setText("Stop Monitoring")
        self._btn_start.setStyleSheet("""
            QPushButton { background-color: #ef4444; color: #000000; border: none; font-weight: 700; border-radius: 8px; }
            QPushButton:hover { background-color: #f87171; }
        """)

    def _on_measurement(self, m: Measurement):
        self._lat_chart.add_value(m.latency_ms)
        self._loss_chart.add_value(m.packet_loss_pct)
        self._bw_chart.add_value(m.bandwidth_mbps)
        self._jitter_chart.add_value(m.jitter_ms)

        self._stat_labels["latency"].setText(f"{m.latency_ms:.1f} ms")
        self._stat_labels["loss"].setText(f"{m.packet_loss_pct:.2f} %")
        self._stat_labels["bandwidth"].setText(f"{m.bandwidth_mbps:.2f} Mbps")
        self._stat_labels["jitter"].setText(f"{m.jitter_ms:.1f} ms")

        self._repo.save_measurement(m)

        if self._engine and self._engine.baseline:
            cs = score_congestion(m, self._engine.baseline, self._recent_scores)
            self._recent_scores.append(cs.score)
            self._gauge.set_score(cs.score, cs.severity)
            self._stat_labels["trend"].setText(cs.trend)
            self._stat_labels["dominant"].setText(cs.dominant_signal.replace("_", " ").title())

    def _on_baseline(self, b):
        self._repo.save_baseline(b)