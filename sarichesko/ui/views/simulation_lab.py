import time
import uuid
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QProgressBar, QGraphicsOpacityEffect,
    QScrollArea, QGridLayout, QSpinBox,
)
from PySide6.QtCore import Qt, QThread, Signal, QPropertyAnimation, QEasingCurve

from ..widgets.latency_chart import LatencyChartWidget
from ...simulation.engine_base import SimConfig, AlgorithmType, SimulationResult
from ...simulation.python_sim import PythonSimulationEngine
from ...simulation.scenarios.base_scenario import SCENARIOS
from ...storage.db import get_connection, init_db
from ...storage.repository import Repository
from ...storage.models import SimulationResult as SimResultModel


ALGO_COLORS = {
    AlgorithmType.LEAKY_BUCKET: "#00f0ff",
    AlgorithmType.TOKEN_BUCKET: "#a78bfa",
    AlgorithmType.RED: "#f59e0b",
    AlgorithmType.CODEL: "#00e5a3",
}


class SimWorker(QThread):
    progress = Signal(str, int)
    complete = Signal(object)
    error = Signal(str)

    def __init__(self, config: SimConfig):
        super().__init__()
        self._config = config

    def run(self):
        try:
            self.progress.emit("Initializing simulation engine...", 10)
            engine = PythonSimulationEngine()
            self.progress.emit(f"Running {self._config.scenario} with {self._config.algorithm.value}...", 30)
            result = engine.run(self._config)
            self.progress.emit("Simulation complete!", 100)
            self.complete.emit(result)
        except Exception as e:
            self.error.emit(str(e))


def _metric_card(label: str, unit: str, color: str) -> tuple[QFrame, QLabel]:
    card = QFrame()
    card.setObjectName("card")
    card.setMinimumHeight(100)
    cl = QVBoxLayout(card)
    cl.setContentsMargins(18, 14, 18, 14)
    cl.setSpacing(6)

    lbl = QLabel(label)
    lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")

    val_row = QHBoxLayout()
    val_row.setSpacing(4)
    val_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBaseline)

    val = QLabel("—")
    val.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {color};")

    ulbl = QLabel(unit)
    ulbl.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {color}; padding-top: 8px;")

    val_row.addWidget(val)
    val_row.addWidget(ulbl)

    cl.addWidget(lbl)
    cl.addLayout(val_row)
    return card, val


class SimulationLabView(QWidget):
    def __init__(self):
        super().__init__()
        self._worker: SimWorker = None
        self._last_result: SimulationResult = None

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #000000; border: none; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        # Header
        title = QLabel("Simulation Lab")
        title.setStyleSheet("font-size: 26px; font-weight: 800; color: #ffffff;")
        subtitle = QLabel("Safe sandbox — test congestion algorithms on synthetic traffic without touching your real network")
        subtitle.setStyleSheet("font-size: 13px; color: #64748b;")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(4)

        # Config Card
        config_card = QFrame()
        config_card.setObjectName("card")
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(22, 18, 22, 18)
        config_layout.setSpacing(16)

        config_title = QLabel("SIMULATION PARAMETERS")
        config_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        config_layout.addWidget(config_title)

        # Scenario description
        self._scenario_desc = QLabel("")
        self._scenario_desc.setStyleSheet("font-size: 12px; color: #475569;")
        self._scenario_desc.setWordWrap(True)

        params_row = QHBoxLayout()
        params_row.setSpacing(14)

        # Scenario
        scen_col = QVBoxLayout()
        scen_col.setSpacing(4)
        lbl_s = QLabel("Scenario")
        lbl_s.setStyleSheet("font-size: 12px; font-weight: 600; color: #94a3b8;")
        scen_col.addWidget(lbl_s)
        self._scenario_combo = QComboBox()
        self._scenario_combo.setFixedHeight(36)
        self._scenario_combo.setMinimumWidth(160)
        for key, info in SCENARIOS.items():
            self._scenario_combo.addItem(info["name"], key)
        self._scenario_combo.currentIndexChanged.connect(self._update_scenario_desc)
        scen_col.addWidget(self._scenario_combo)
        params_row.addLayout(scen_col)

        # Algorithm
        algo_col = QVBoxLayout()
        algo_col.setSpacing(4)
        lbl_a = QLabel("Algorithm")
        lbl_a.setStyleSheet("font-size: 12px; font-weight: 600; color: #94a3b8;")
        algo_col.addWidget(lbl_a)
        self._algo_combo = QComboBox()
        self._algo_combo.setFixedHeight(36)
        self._algo_combo.setMinimumWidth(160)
        for algo in [AlgorithmType.LEAKY_BUCKET, AlgorithmType.TOKEN_BUCKET, AlgorithmType.RED, AlgorithmType.CODEL]:
            self._algo_combo.addItem(algo.value, algo)
        algo_col.addWidget(self._algo_combo)
        params_row.addLayout(algo_col)

        # Duration
        dur_col = QVBoxLayout()
        dur_col.setSpacing(4)
        lbl_d = QLabel("Duration (s)")
        lbl_d.setStyleSheet("font-size: 12px; font-weight: 600; color: #94a3b8;")
        dur_col.addWidget(lbl_d)
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(1, 30)
        self._duration_spin.setValue(5)
        self._duration_spin.setFixedHeight(36)
        dur_col.addWidget(self._duration_spin)
        params_row.addLayout(dur_col)

        # Link BW
        bw_col = QVBoxLayout()
        bw_col.setSpacing(4)
        lbl_b = QLabel("Link (Mbps)")
        lbl_b.setStyleSheet("font-size: 12px; font-weight: 600; color: #94a3b8;")
        bw_col.addWidget(lbl_b)
        self._bw_spin = QSpinBox()
        self._bw_spin.setRange(1, 1000)
        self._bw_spin.setValue(10)
        self._bw_spin.setFixedHeight(36)
        bw_col.addWidget(self._bw_spin)
        params_row.addLayout(bw_col)

        # Queue Size
        qs_col = QVBoxLayout()
        qs_col.setSpacing(4)
        lbl_q = QLabel("Queue Size")
        lbl_q.setStyleSheet("font-size: 12px; font-weight: 600; color: #94a3b8;")
        qs_col.addWidget(lbl_q)
        self._queue_spin = QSpinBox()
        self._queue_spin.setRange(10, 1000)
        self._queue_spin.setValue(100)
        self._queue_spin.setFixedHeight(36)
        qs_col.addWidget(self._queue_spin)
        params_row.addLayout(qs_col)

        config_layout.addLayout(params_row)
        config_layout.addWidget(self._scenario_desc)

        # Run button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_run = QPushButton("Run Simulation")
        self._btn_run.setObjectName("primary_btn")
        self._btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_run.setFixedHeight(40)
        self._btn_run.setFixedWidth(180)
        self._btn_run.clicked.connect(self._run_simulation)
        btn_row.addWidget(self._btn_run)
        config_layout.addLayout(btn_row)

        layout.addWidget(config_card)

        # Progress
        self._progress_frame = QFrame()
        self._progress_frame.setObjectName("card")
        self._progress_frame.setVisible(False)
        prog_layout = QVBoxLayout(self._progress_frame)
        prog_layout.setContentsMargins(20, 14, 20, 14)
        prog_layout.setSpacing(8)

        self._progress_label = QLabel("")
        self._progress_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #94a3b8;")
        prog_layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setStyleSheet("""
            QProgressBar { background-color: #121420; border: none; border-radius: 2px; }
            QProgressBar::chunk { background-color: #a78bfa; border-radius: 2px; }
        """)
        prog_layout.addWidget(self._progress_bar)
        layout.addWidget(self._progress_frame)

        # Results
        self._results_widget = QWidget()
        self._results_widget.setVisible(False)
        results_layout = QVBoxLayout(self._results_widget)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.setSpacing(14)

        # Result header with algo name
        self._result_header = QLabel("")
        self._result_header.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        results_layout.addWidget(self._result_header)

        # Metrics row
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(12)
        self._metric_values = {}

        metrics_info = [
            ("throughput", "THROUGHPUT", "Mbps", "#00f0ff"),
            ("avg_latency", "AVG LATENCY", "ms", "#a78bfa"),
            ("loss", "PACKET LOSS", "%", "#ef4444"),
            ("fairness", "FAIRNESS", "", "#00e5a3"),
            ("total_pkts", "TOTAL PKTS", "", "#ffffff"),
            ("dropped", "DROPPED", "", "#f59e0b"),
        ]

        for i, (key, label, unit, color) in enumerate(metrics_info):
            card, val = _metric_card(label, unit, color)
            metrics_grid.addWidget(card, 0, i)
            self._metric_values[key] = val

        results_layout.addLayout(metrics_grid)

        # Charts
        charts_row = QHBoxLayout()
        charts_row.setSpacing(12)

        self._latency_chart = LatencyChartWidget("Packet Latency", "ms", "#a78bfa", max_points=500)
        self._latency_chart.setMinimumHeight(200)
        self._queue_chart = LatencyChartWidget("Queue Depth", "pkts", "#f59e0b", max_points=500)
        self._queue_chart.setMinimumHeight(200)

        charts_row.addWidget(self._latency_chart)
        charts_row.addWidget(self._queue_chart)
        results_layout.addLayout(charts_row)

        self._engine_label = QLabel("")
        self._engine_label.setStyleSheet("font-size: 11px; color: #334155;")
        results_layout.addWidget(self._engine_label)

        layout.addWidget(self._results_widget)
        layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._update_scenario_desc()

        # Fade in
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._anim = QPropertyAnimation(self._opacity, b"opacity")
        self._anim.setDuration(350)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def _update_scenario_desc(self):
        key = self._scenario_combo.currentData()
        if key and key in SCENARIOS:
            self._scenario_desc.setText(SCENARIOS[key]["description"])

    def _run_simulation(self):
        scenario_key = self._scenario_combo.currentData()
        algo = self._algo_combo.currentData()
        if not scenario_key or not algo:
            return

        config = SimConfig(
            scenario=scenario_key,
            algorithm=algo,
            duration_s=self._duration_spin.value(),
            link_bandwidth_mbps=self._bw_spin.value(),
            queue_size=self._queue_spin.value(),
        )

        self._btn_run.setEnabled(False)
        self._btn_run.setText("Simulating...")
        self._results_widget.setVisible(False)
        self._progress_frame.setVisible(True)
        self._progress_bar.setValue(0)
        self._progress_label.setText("Starting simulation...")
        self._progress_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #94a3b8;")

        self._worker = SimWorker(config)
        self._worker.progress.connect(self._on_progress)
        self._worker.complete.connect(self._on_complete)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_progress(self, text: str, value: int):
        self._progress_label.setText(text)
        self._progress_bar.setValue(value)

    def _on_complete(self, result: SimulationResult):
        self._btn_run.setEnabled(True)
        self._btn_run.setText("Run Simulation")
        self._progress_frame.setVisible(False)
        self._last_result = result

        m = result.metrics
        self._metric_values["throughput"].setText(f"{m.throughput_mbps:.2f}")
        self._metric_values["avg_latency"].setText(f"{m.avg_latency_ms:.1f}")
        self._metric_values["loss"].setText(f"{m.loss_pct:.2f}")
        self._metric_values["fairness"].setText(f"{m.fairness_index:.3f}")
        self._metric_values["total_pkts"].setText(f"{m.total_packets:,}")
        self._metric_values["dropped"].setText(f"{m.dropped_packets:,}")

        algo_color = ALGO_COLORS.get(result.config.algorithm, "#00f0ff")
        scenario_name = SCENARIOS.get(result.scenario, {}).get("name", result.scenario)
        self._result_header.setText(f"{result.algorithm}  on  {scenario_name}")
        self._result_header.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {algo_color};")

        self._latency_chart._data.clear()
        for _, lat in result.latency_over_time[:500]:
            self._latency_chart.add_value(lat)

        self._queue_chart._data.clear()
        for _, depth in result.queue_depth_over_time[:500]:
            self._queue_chart.add_value(depth)

        self._engine_label.setText(
            f"Engine: {result.engine_used}  •  Duration: {result.duration_s}s  •  "
            f"Link: {result.config.link_bandwidth_mbps} Mbps  •  Queue: {result.config.queue_size}"
        )

        try:
            conn = get_connection()
            init_db(conn)
            repo = Repository(conn)
            repo.save_simulation_result(SimResultModel(
                id=str(uuid.uuid4()),
                timestamp=time.time(),
                scenario=result.scenario,
                algorithm=result.algorithm,
                engine_used=result.engine_used,
                parameters=json.dumps({"queue_size": result.config.queue_size, "link_mbps": result.config.link_bandwidth_mbps}),
                throughput_mbps=m.throughput_mbps,
                avg_latency_ms=m.avg_latency_ms,
                loss_pct=m.loss_pct,
                fairness_index=m.fairness_index,
                metrics_detail=json.dumps({"max_latency": m.max_latency_ms, "max_queue": m.max_queue_depth}),
            ))
            conn.close()
        except Exception:
            pass

        self._results_widget.setVisible(True)
        self._worker = None

    def _on_error(self, msg: str):
        self._btn_run.setEnabled(True)
        self._btn_run.setText("Run Simulation")
        self._progress_label.setText(f"Error: {msg}")
        self._progress_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #ef4444;")
        self._worker = None