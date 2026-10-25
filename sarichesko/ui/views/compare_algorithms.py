import time
import uuid
import json
from typing import Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QComboBox, QProgressBar, QGraphicsOpacityEffect,
    QScrollArea, QGridLayout, QSpinBox, QFileDialog,
)
from PySide6.QtCore import Qt, QThread, Signal, QPropertyAnimation, QEasingCurve

from ..widgets.algo_comparison_chart import AlgoBarChartWidget
from ..widgets.engine_selector import EngineSelector
from ...simulation.engine_base import SimConfig, AlgorithmType, SimulationResult
from ...simulation.scenarios.base_scenario import SCENARIOS
from ...storage.db import get_connection, init_db
from ...storage.repository import Repository
from ...storage.models import SimulationResult as SimResultModel
from ...utils.export import export_rows_to_csv, default_export_dir
from ..theme import theme_manager, Palette, style


ALGOS = [AlgorithmType.LEAKY_BUCKET, AlgorithmType.TOKEN_BUCKET, AlgorithmType.RED, AlgorithmType.CODEL]


def algo_colors(p: Palette) -> dict:
    return {
        "Leaky Bucket": p.accent,
        "Token Bucket": p.purple,
        "RED": p.warning,
        "CoDel": p.success,
    }


class CompareWorker(QThread):
    """Runs the same synthetic scenario through all four algorithms back-to-back,
    so the results are directly comparable (identical traffic, link, and queue)."""

    progress = Signal(str, int)
    complete = Signal(dict)   # {algo_value: SimulationResult}
    error = Signal(str)

    def __init__(self, scenario: str, duration_s: float, link_mbps: float, queue_size: int, engine):
        super().__init__()
        self._scenario = scenario
        self._duration = duration_s
        self._link = link_mbps
        self._queue = queue_size
        self._engine = engine

    def run(self):
        try:
            results: dict[str, SimulationResult] = {}
            for i, algo in enumerate(ALGOS):
                pct = int((i / len(ALGOS)) * 90) + 5
                self.progress.emit(f"Simulating {algo.value}...", pct)
                config = SimConfig(
                    scenario=self._scenario,
                    algorithm=algo,
                    duration_s=self._duration,
                    link_bandwidth_mbps=self._link,
                    queue_size=self._queue,
                )
                results[algo.value] = self._engine.run(config)
            self.progress.emit("Comparison complete!", 100)
            self.complete.emit(results)
        except Exception as e:
            self.error.emit(str(e))


def _composite_scores(current: dict) -> dict:
    """A comparative-only ranking for THIS scenario run: normalizes each metric
    0-1 across the four algorithms and averages them equally. This is NOT the
    same as the live diagnosis recommendation engine (which uses real ISP and
    queueing evidence) -- it's purely a way to summarize a single simulation."""
    if not current:
        return {}

    def norm(key, invert=False):
        vals = [v[key] for v in current.values()]
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or 1.0
        out = {}
        for a, v in current.items():
            n = (v[key] - lo) / span
            out[a] = (1 - n) if invert else n
        return out

    nt = norm("throughput")
    nl = norm("latency", invert=True)
    npkt = norm("loss", invert=True)
    nf = norm("fairness")
    return {a: round((nt[a] + nl[a] + npkt[a] + nf[a]) / 4, 3) for a in current}


class CompareAlgorithmsView(QWidget):
    def __init__(self):
        super().__init__()
        self._worker: Optional[CompareWorker] = None
        self._current: dict[str, dict] = {}   # algo_name -> {throughput, latency, loss, fairness, engine, timestamp}

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        style(scroll, lambda p: f"QScrollArea {{ background: {p.bg}; border: none; }}")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        # Header
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Compare Algorithms")
        style(title, lambda p: f"font-size: 26px; font-weight: 800; color: {p.text_strong};")
        subtitle = QLabel("Run the same synthetic traffic through all four approaches to see which fits best")
        style(subtitle, lambda p: f"font-size: 13px; color: {p.text_muted};")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        self._btn_export = QPushButton("Export CSV")
        self._btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_export.setFixedHeight(36)
        self._btn_export.setEnabled(False)
        self._btn_export.clicked.connect(self._export_csv)
        header.addWidget(self._btn_export)

        layout.addLayout(header)

        # Config card
        config_card = QFrame()
        config_card.setObjectName("card")
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(22, 18, 22, 18)
        config_layout.setSpacing(16)

        config_title = QLabel("COMPARISON PARAMETERS")
        style(config_title, lambda p: f"font-size: 11px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")
        config_layout.addWidget(config_title)

        self._scenario_desc = QLabel("")
        style(self._scenario_desc, lambda p: f"font-size: 12px; color: {p.text_faint};")
        self._scenario_desc.setWordWrap(True)

        params_row = QHBoxLayout()
        params_row.setSpacing(14)

        scen_col = QVBoxLayout()
        scen_col.setSpacing(4)
        lbl_s = QLabel("Scenario")
        style(lbl_s, lambda p: f"font-size: 12px; font-weight: 600; color: {p.text_secondary};")
        scen_col.addWidget(lbl_s)
        self._scenario_combo = QComboBox()
        self._scenario_combo.setFixedHeight(36)
        self._scenario_combo.setMinimumWidth(180)
        for key, info in SCENARIOS.items():
            self._scenario_combo.addItem(info["name"], key)
        self._scenario_combo.currentIndexChanged.connect(self._on_scenario_changed)
        scen_col.addWidget(self._scenario_combo)
        params_row.addLayout(scen_col)

        dur_col = QVBoxLayout()
        dur_col.setSpacing(4)
        lbl_d = QLabel("Duration (s)")
        style(lbl_d, lambda p: f"font-size: 12px; font-weight: 600; color: {p.text_secondary};")
        dur_col.addWidget(lbl_d)
        self._duration_spin = QSpinBox()
        self._duration_spin.setRange(1, 15)
        self._duration_spin.setValue(5)
        self._duration_spin.setFixedHeight(36)
        dur_col.addWidget(self._duration_spin)
        params_row.addLayout(dur_col)

        bw_col = QVBoxLayout()
        bw_col.setSpacing(4)
        lbl_b = QLabel("Link (Mbps)")
        style(lbl_b, lambda p: f"font-size: 12px; font-weight: 600; color: {p.text_secondary};")
        bw_col.addWidget(lbl_b)
        self._bw_spin = QSpinBox()
        self._bw_spin.setRange(1, 1000)
        self._bw_spin.setValue(10)
        self._bw_spin.setFixedHeight(36)
        bw_col.addWidget(self._bw_spin)
        params_row.addLayout(bw_col)

        qs_col = QVBoxLayout()
        qs_col.setSpacing(4)
        lbl_q = QLabel("Queue Size")
        style(lbl_q, lambda p: f"font-size: 12px; font-weight: 600; color: {p.text_secondary};")
        qs_col.addWidget(lbl_q)
        self._queue_spin = QSpinBox()
        self._queue_spin.setRange(10, 1000)
        self._queue_spin.setValue(100)
        self._queue_spin.setFixedHeight(36)
        qs_col.addWidget(self._queue_spin)
        params_row.addLayout(qs_col)

        config_layout.addLayout(params_row)
        config_layout.addWidget(self._scenario_desc)

        # Engine selector
        self._engine_selector = EngineSelector()
        config_layout.addWidget(self._engine_selector)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_run = QPushButton("Run Comparison (all 4 algorithms)")
        self._btn_run.setObjectName("primary_btn")
        self._btn_run.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_run.setFixedHeight(40)
        self._btn_run.clicked.connect(self._run_comparison)
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
        style(self._progress_label, lambda p: f"font-size: 13px; font-weight: 600; color: {p.text_secondary};")
        prog_layout.addWidget(self._progress_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setTextVisible(False)
        style(self._progress_bar, lambda p: f"""
            QProgressBar {{ background-color: {p.track}; border: none; border-radius: 2px; }}
            QProgressBar::chunk {{ background-color: {p.purple}; border-radius: 2px; }}
        """)
        prog_layout.addWidget(self._progress_bar)
        layout.addWidget(self._progress_frame)

        # Winner callout
        self._winner_card = QFrame()
        self._winner_card.setObjectName("card")
        self._winner_card.setVisible(False)
        wl = QVBoxLayout(self._winner_card)
        wl.setContentsMargins(20, 16, 20, 16)
        wl.setSpacing(6)

        wl_title = QLabel("BEST FIT FOR THIS SCENARIO")
        style(wl_title, lambda p: f"font-size: 11px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")
        wl.addWidget(wl_title)

        self._winner_label = QLabel("—")
        style(self._winner_label, lambda p: f"font-size: 22px; font-weight: 800; color: {p.accent};")
        wl.addWidget(self._winner_label)

        self._winner_reason = QLabel("")
        style(self._winner_reason, lambda p: f"font-size: 12px; color: {p.text_secondary};")
        self._winner_reason.setWordWrap(True)
        wl.addWidget(self._winner_reason)

        disclaimer = QLabel(
            "Comparative ranking for this simulated scenario only — it is not the same as the live "
            "network diagnosis recommendation, which also weighs real ISP and queueing evidence."
        )
        style(disclaimer, lambda p: f"font-size: 10px; color: {p.text_faint}; font-style: italic;")
        disclaimer.setWordWrap(True)
        wl.addWidget(disclaimer)

        layout.addWidget(self._winner_card)

        # Mixed-engines warning
        self._mixed_engines_label = QLabel(
            "\u26a0 Mixed engines \u2014 results are not directly comparable"
        )
        style(self._mixed_engines_label, lambda p: (
            f"font-size: 12px; font-weight: 600; color: {p.warning}; "
            f"background: {p.warning_bg}; border: 1px solid {p.warning}; "
            f"border-radius: 6px; padding: 8px 12px;"
        ))
        self._mixed_engines_label.setWordWrap(True)
        self._mixed_engines_label.setVisible(False)
        layout.addWidget(self._mixed_engines_label)

        # Chart grid (one small-multiple per metric)
        self._charts_widget = QWidget()
        self._charts_widget.setVisible(False)
        charts_grid = QGridLayout(self._charts_widget)
        charts_grid.setSpacing(12)

        self._chart_throughput = AlgoBarChartWidget("THROUGHPUT", "Mbps", higher_is_better=True)
        self._chart_latency = AlgoBarChartWidget("AVG LATENCY", "ms", higher_is_better=False)
        self._chart_loss = AlgoBarChartWidget("PACKET LOSS", "%", higher_is_better=False)
        self._chart_fairness = AlgoBarChartWidget("FAIRNESS", "index", higher_is_better=True)

        for col, chart in enumerate((self._chart_throughput, self._chart_latency,
                                      self._chart_loss, self._chart_fairness)):
            frame = QFrame()
            frame.setObjectName("card")
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(4, 4, 4, 4)
            fl.addWidget(chart)
            charts_grid.addWidget(frame, 0, col)

        layout.addWidget(self._charts_widget)

        # Detail table
        self._table_card = QFrame()
        self._table_card.setObjectName("card")
        self._table_card.setVisible(False)
        tl = QVBoxLayout(self._table_card)
        tl.setContentsMargins(20, 16, 20, 16)
        tl.setSpacing(10)

        table_title = QLabel("EXACT VALUES")
        style(table_title, lambda p: f"font-size: 11px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")
        tl.addWidget(table_title)

        self._table_grid = QGridLayout()
        self._table_grid.setSpacing(8)
        tl.addLayout(self._table_grid)

        layout.addWidget(self._table_card)
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

        theme_manager.changed.connect(lambda _: self._render())
        self._load_latest_for_scenario()

    def showEvent(self, event):
        super().showEvent(event)
        if not self._current:
            self._load_latest_for_scenario()

    def _update_scenario_desc(self):
        key = self._scenario_combo.currentData()
        if key and key in SCENARIOS:
            self._scenario_desc.setText(SCENARIOS[key]["description"])

    def _on_scenario_changed(self):
        self._update_scenario_desc()
        self._current = {}
        self._load_latest_for_scenario()

    def _load_latest_for_scenario(self):
        """On open (or scenario switch), show the most recent stored result per
        algorithm for this scenario, if any exist, without forcing a re-run."""
        scenario_key = self._scenario_combo.currentData()
        if not scenario_key:
            return
        try:
            conn = get_connection()
            init_db(conn)
            repo = Repository(conn)
            current = {}
            for algo in ALGOS:
                row = repo.get_latest_simulation_result(scenario_key, algo.value)
                if row:
                    current[algo.value] = {
                        "throughput": row["throughput_mbps"] or 0.0,
                        "latency": row["avg_latency_ms"] or 0.0,
                        "loss": row["loss_pct"] or 0.0,
                        "fairness": row["fairness_index"] or 0.0,
                        "engine": row["engine_used"] or "python_fallback",
                        "timestamp": row["timestamp"],
                    }
            conn.close()
            if current:
                self._current = current
                self._render()
        except Exception:
            pass

    def _run_comparison(self):
        scenario_key = self._scenario_combo.currentData()
        if not scenario_key:
            return

        p = theme_manager.palette
        self._btn_run.setEnabled(False)
        self._btn_run.setText("Comparing...")
        self._winner_card.setVisible(False)
        self._charts_widget.setVisible(False)
        self._table_card.setVisible(False)
        self._progress_frame.setVisible(True)
        self._progress_bar.setValue(0)
        self._progress_label.setText("Starting comparison...")
        self._progress_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {p.text_secondary};")

        self._worker = CompareWorker(
            scenario=scenario_key,
            duration_s=self._duration_spin.value(),
            link_mbps=self._bw_spin.value(),
            queue_size=self._queue_spin.value(),
            engine=self._engine_selector.build_engine(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.complete.connect(self._on_complete)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_progress(self, text: str, value: int):
        self._progress_label.setText(text)
        self._progress_bar.setValue(value)

    def _on_complete(self, results: dict):
        self._btn_run.setEnabled(True)
        self._btn_run.setText("Run Comparison (all 4 algorithms)")
        self._progress_frame.setVisible(False)

        scenario_key = self._scenario_combo.currentData()
        now = time.time()

        current = {}
        for algo_name, result in results.items():
            m = result.metrics
            current[algo_name] = {
                "throughput": m.throughput_mbps,
                "latency": m.avg_latency_ms,
                "loss": m.loss_pct,
                "fairness": m.fairness_index,
                "engine": result.engine_used,
                "timestamp": now,
            }
        self._current = current

        # Persist each run so History and future comparisons can see it
        try:
            conn = get_connection()
            init_db(conn)
            repo = Repository(conn)
            for algo_name, result in results.items():
                m = result.metrics
                repo.save_simulation_result(SimResultModel(
                    id=str(uuid.uuid4()),
                    timestamp=now,
                    scenario=scenario_key,
                    algorithm=algo_name,
                    engine_used=result.engine_used,
                    parameters=json.dumps({
                        "queue_size": result.config.queue_size,
                        "link_mbps": result.config.link_bandwidth_mbps,
                        "duration_s": result.config.duration_s,
                    }),
                    throughput_mbps=m.throughput_mbps,
                    avg_latency_ms=m.avg_latency_ms,
                    loss_pct=m.loss_pct,
                    fairness_index=m.fairness_index,
                    metrics_detail=json.dumps({
                        "max_latency": m.max_latency_ms,
                        "max_queue": m.max_queue_depth,
                    }),
                ))
            conn.close()
        except Exception:
            pass

        self._render()

    def _on_error(self, msg: str):
        self._btn_run.setEnabled(True)
        self._btn_run.setText("Run Comparison (all 4 algorithms)")
        self._progress_label.setText(f"Error: {msg}")
        self._progress_label.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {theme_manager.palette.danger};")

    def _render(self):
        if not self._current:
            return

        p = theme_manager.palette
        algo_c = algo_colors(p)

        def entries(key):
            return [(a, v[key], algo_c.get(a, p.accent)) for a, v in self._current.items()]

        self._chart_throughput.set_data(entries("throughput"))
        self._chart_latency.set_data(entries("latency"))
        self._chart_loss.set_data(entries("loss"))
        self._chart_fairness.set_data(entries("fairness"))
        self._charts_widget.setVisible(True)

        scores = _composite_scores(self._current)
        if scores:
            winner = max(scores, key=scores.get)
            self._winner_label.setText(winner)
            style(self._winner_label, lambda p, w=winner: f"font-size: 22px; font-weight: 800; color: {algo_colors(p).get(w, p.accent)};")
            self._winner_reason.setText(
                f"Composite score {scores[winner]:.2f} of 1.00 — best overall balance of throughput, "
                f"latency, loss, and fairness among the four in this run."
            )
            self._winner_card.setVisible(True)

        # Mixed-engines check
        engines_used = set(v["engine"] for v in self._current.values())
        self._mixed_engines_label.setVisible(len(engines_used) > 1)

        # Rebuild the exact-values table
        while self._table_grid.count():
            item = self._table_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        headers = ["Algorithm", "Throughput (Mbps)", "Latency (ms)", "Loss (%)", "Fairness", "Score", "Engine"]
        for col, h in enumerate(headers):
            lbl = QLabel(h)
            style(lbl, lambda p: f"font-size: 10px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.4px;")
            self._table_grid.addWidget(lbl, 0, col)

        for row, (algo_name, v) in enumerate(self._current.items(), start=1):
            name_lbl = QLabel(algo_name)
            style(name_lbl, lambda p, a=algo_name: f"font-size: 12px; font-weight: 700; color: {algo_colors(p).get(a, p.text_strong)};")
            self._table_grid.addWidget(name_lbl, row, 0)

            values = [f"{v['throughput']:.2f}", f"{v['latency']:.1f}",
                      f"{v['loss']:.2f}", f"{v['fairness']:.3f}",
                      f"{scores.get(algo_name, 0):.3f}", v["engine"]]
            for col, val in enumerate(values, start=1):
                lbl = QLabel(val)
                style(lbl, lambda p: f"font-size: 12px; color: {p.text};")
                self._table_grid.addWidget(lbl, row, col)

        self._table_card.setVisible(True)
        self._btn_export.setEnabled(True)

    def _export_csv(self):
        if not self._current:
            return
        scenario_key = self._scenario_combo.currentData()
        scores = _composite_scores(self._current)
        rows = []
        for algo_name, v in self._current.items():
            rows.append({
                "scenario": scenario_key,
                "algorithm": algo_name,
                "throughput_mbps": v["throughput"],
                "avg_latency_ms": v["latency"],
                "loss_pct": v["loss"],
                "fairness_index": v["fairness"],
                "composite_score": scores.get(algo_name, 0),
                "engine_used": v["engine"],
                "timestamp": v["timestamp"],
            })

        default_name = str(default_export_dir() / f"comparison_{scenario_key}_{int(time.time())}.csv")
        path, _ = QFileDialog.getSaveFileName(self, "Export Comparison", default_name, "CSV Files (*.csv)")
        if not path:
            return
        try:
            export_rows_to_csv(rows, path)
        except Exception:
            pass