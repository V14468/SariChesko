from typing import Callable
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGraphicsOpacityEffect, QGridLayout, QScrollArea,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve

from ..widgets.congestion_gauge import CongestionGaugeWidget
from ...storage.db import get_connection, init_db
from ...storage.repository import Repository
from ..theme import theme_manager, Palette, style


def _stat_card(
    title: str,
    value: str,
    unit: str,
    color_fn: Callable[[Palette], str],
    footnote: str,
) -> tuple[QFrame, QLabel, QLabel]:
    card = QFrame()
    card.setObjectName("card")
    card.setMinimumHeight(105)
    cl = QVBoxLayout(card)
    cl.setContentsMargins(18, 14, 18, 14)
    cl.setSpacing(6)

    lbl_t = QLabel(title)
    style(lbl_t, lambda p: f"font-size: 10px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")

    val_row = QHBoxLayout()
    val_row.setSpacing(4)
    val_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBaseline)

    lbl_v = QLabel(value)
    style(lbl_v, lambda p: f"font-size: 26px; font-weight: 800; color: {color_fn(p)};")

    lbl_u = QLabel(unit)
    style(lbl_u, lambda p: f"font-size: 12px; font-weight: 600; color: {color_fn(p)}; padding-top: 8px;")

    val_row.addWidget(lbl_v)
    val_row.addWidget(lbl_u)

    lbl_f = QLabel(footnote)
    style(lbl_f, lambda p: f"font-size: 11px; color: {p.text_faint};")

    cl.addWidget(lbl_t)
    cl.addLayout(val_row)
    cl.addWidget(lbl_f)
    return card, lbl_v, lbl_f


def _status_row(
    label: str,
    status: str,
    color_fn: Callable[[Palette], str],
) -> tuple[QHBoxLayout, QLabel]:
    row = QHBoxLayout()
    row.setSpacing(10)

    dot = QLabel("●")
    style(dot, lambda p: f"font-size: 10px; color: {color_fn(p)};")
    dot.setFixedWidth(14)

    lbl = QLabel(label)
    style(lbl, lambda p: f"font-size: 13px; font-weight: 600; color: {p.text};")

    val = QLabel(status)
    style(val, lambda p: f"font-size: 13px; font-weight: 600; color: {color_fn(p)};")
    val.setAlignment(Qt.AlignmentFlag.AlignRight)

    row.addWidget(dot)
    row.addWidget(lbl)
    row.addStretch()
    row.addWidget(val)
    return row, val


class DashboardView(QWidget):
    def __init__(self):
        super().__init__()
        self._last_diagnostic = None

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
        title = QLabel("Dashboard")
        style(title, lambda p: f"font-size: 26px; font-weight: 800; color: {p.text_strong};")
        subtitle = QLabel("Real-time network health overview")
        style(subtitle, lambda p: f"font-size: 13px; color: {p.text_muted};")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        self._btn_diag = QPushButton("Run Diagnostic")
        self._btn_diag.setObjectName("primary_btn")
        self._btn_diag.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_diag.setFixedHeight(36)
        self._btn_diag.clicked.connect(self._go_to_diagnose)
        header.addWidget(self._btn_diag)

        layout.addLayout(header)

        # Metric Cards
        cards_grid = QGridLayout()
        cards_grid.setSpacing(12)
        self._metric_values = {}
        self._metric_footnotes = {}

        card_info = [
            ("LATENCY", "—", "ms", lambda p: p.accent, "No data yet"),
            ("PACKET LOSS", "—", "%", lambda p: p.danger, "No data yet"),
            ("BANDWIDTH", "—", "Mbps", lambda p: p.purple, "No data yet"),
            ("JITTER", "—", "ms", lambda p: p.warning, "No data yet"),
        ]
        keys = ["latency", "packet_loss", "bandwidth", "jitter"]
        for i, (t, v, u, c_fn, f) in enumerate(card_info):
            card, val_label, foot_label = _stat_card(t, v, u, c_fn, f)
            cards_grid.addWidget(card, 0, i)
            self._metric_values[keys[i]] = val_label
            self._metric_footnotes[keys[i]] = foot_label

        layout.addLayout(cards_grid)

        # Two-column: System Status + Congestion Score
        two_col = QHBoxLayout()
        two_col.setSpacing(14)

        # System Status
        status_card = QFrame()
        status_card.setObjectName("card")
        sl = QVBoxLayout(status_card)
        sl.setContentsMargins(20, 16, 20, 16)
        sl.setSpacing(12)

        st_title = QLabel("SYSTEM STATUS")
        style(st_title, lambda p: f"font-size: 11px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")
        sl.addWidget(st_title)

        self._status_values = {}
        statuses = [
            ("Monitor Engine", "Idle", lambda p: p.text_muted),
            ("ISP Probe", "Ready", lambda p: p.success),
            ("Congestion Scorer", "Idle", lambda p: p.text_muted),
            ("Traffic Controller", "Inactive", lambda p: p.text_muted),
            ("Database", "Connected", lambda p: p.success),
        ]
        for lbl, val, col_fn in statuses:
            row, val_lbl = _status_row(lbl, val, col_fn)
            sl.addLayout(row)
            self._status_values[lbl] = val_lbl

        two_col.addWidget(status_card, 1)

        # Congestion Gauge
        gauge_card = QFrame()
        gauge_card.setObjectName("card")
        gl = QVBoxLayout(gauge_card)
        gl.setContentsMargins(20, 16, 20, 16)

        g_title = QLabel("CONGESTION SCORE")
        style(g_title, lambda p: f"font-size: 11px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")
        gl.addWidget(g_title)

        self._gauge = CongestionGaugeWidget()
        self._gauge.setMinimumSize(180, 180)
        gl.addWidget(self._gauge, 0, Qt.AlignmentFlag.AlignCenter)

        self._score_hint = QLabel("Run a diagnostic to generate a score")
        style(self._score_hint, lambda p: f"font-size: 11px; color: {p.text_fainter};")
        self._score_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        gl.addWidget(self._score_hint)

        two_col.addWidget(gauge_card, 1)
        layout.addLayout(two_col)

        # Bottom: Last ISP Result + Recommendation
        bottom = QHBoxLayout()
        bottom.setSpacing(14)

        # ISP summary
        isp_card = QFrame()
        isp_card.setObjectName("card")
        il = QVBoxLayout(isp_card)
        il.setContentsMargins(20, 16, 20, 16)
        il.setSpacing(10)

        isp_title = QLabel("ISP HEALTH")
        style(isp_title, lambda p: f"font-size: 11px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")
        il.addWidget(isp_title)

        self._isp_verdict_label = QLabel("Not tested")
        style(self._isp_verdict_label, lambda p: (
            f"font-size: 18px; font-weight: 700; color: {p.text_faint};"
            if not self._last_diagnostic else
            f"font-size: 18px; font-weight: 700; color: {self._get_isp_color(p)};"
        ))
        il.addWidget(self._isp_verdict_label)

        self._isp_detail_label = QLabel("Run a diagnostic to check ISP health")
        style(self._isp_detail_label, lambda p: f"font-size: 12px; color: {p.text_faint};")
        self._isp_detail_label.setWordWrap(True)
        il.addWidget(self._isp_detail_label)

        self._isp_stats = QLabel("")
        style(self._isp_stats, lambda p: f"font-size: 11px; color: {p.text_muted};")
        il.addWidget(self._isp_stats)
        il.addStretch()

        bottom.addWidget(isp_card, 1)

        # Recommendation
        rec_card = QFrame()
        rec_card.setObjectName("card")
        rl = QVBoxLayout(rec_card)
        rl.setContentsMargins(20, 16, 20, 16)
        rl.setSpacing(8)

        rec_title = QLabel("RECOMMENDATION")
        style(rec_title, lambda p: f"font-size: 11px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")
        rl.addWidget(rec_title)

        self._algo_label = QLabel("Awaiting Diagnostic")
        style(self._algo_label, lambda p: (
            f"font-size: 20px; font-weight: 700; color: {p.text_fainter};"
            if not self._last_diagnostic else
            f"font-size: 20px; font-weight: 700; color: {self._get_algo_color(p)};"
        ))
        rl.addWidget(self._algo_label)

        self._reason_label = QLabel("Run a diagnostic to receive an algorithm recommendation")
        style(self._reason_label, lambda p: f"font-size: 12px; color: {p.text_faint};")
        self._reason_label.setWordWrap(True)
        rl.addWidget(self._reason_label)

        self._algos_avail = QLabel("Available: Leaky Bucket · Token Bucket · RED · CoDel")
        style(self._algos_avail, lambda p: f"font-size: 10px; color: {p.text_fainter}; letter-spacing: 0.3px;")
        rl.addWidget(self._algos_avail)
        rl.addStretch()

        bottom.addWidget(rec_card, 1)
        layout.addLayout(bottom)

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

        theme_manager.changed.connect(lambda _: self._load_latest())
        self._load_latest()

    def _get_isp_color(self, p: Palette) -> str:
        if not self._last_diagnostic:
            return p.text_faint
        isp_verdict = self._last_diagnostic.get("isp_verdict") or "unknown"
        display_map = {
            "healthy": p.success,
            "local_congestion": p.warning,
            "last_mile": p.danger,
            "isp_degradation": p.warning,
            "isp_outage": p.danger,
            "dns_issue": p.danger,
        }
        return display_map.get(isp_verdict, p.text_muted)

    def _get_algo_color(self, p: Palette) -> str:
        if not self._last_diagnostic:
            return p.text_fainter
        algo = self._last_diagnostic.get("recommended_algo")
        if not algo:
            return p.success
        algo_map = {
            "Leaky Bucket": p.accent,
            "Token Bucket": p.purple,
            "RED": p.warning,
            "CoDel": p.success,
        }
        return algo_map.get(algo, p.accent)

    def showEvent(self, event):
        super().showEvent(event)
        self._load_latest()

    def _load_latest(self):
        try:
            conn = get_connection()
            init_db(conn)
            repo = Repository(conn)

            runs = repo.get_diagnostic_runs(limit=1)
            if not runs:
                self._last_diagnostic = None
                conn.close()
                return

            r = runs[0]
            self._last_diagnostic = r

            # Get measurements for this session
            measurements = repo.get_recent_measurements(r["session_id"], limit=20)
            conn.close()

            if measurements:
                lats = [m["latency_ms"] for m in measurements if m["latency_ms"]]
                losses = [m["packet_loss_pct"] for m in measurements if m["packet_loss_pct"] is not None]
                bws = [m["bandwidth_mbps"] for m in measurements if m["bandwidth_mbps"] is not None]
                jits = [m["jitter_ms"] for m in measurements if m["jitter_ms"] is not None]

                if lats:
                    avg_lat = sum(lats) / len(lats)
                    self._metric_values["latency"].setText(f"{avg_lat:.1f}")
                    self._metric_footnotes["latency"].setText("From last diagnostic")

                if losses:
                    avg_loss = sum(losses) / len(losses)
                    self._metric_values["packet_loss"].setText(f"{avg_loss:.2f}")
                    self._metric_footnotes["packet_loss"].setText("From last diagnostic")

                if bws:
                    avg_bw = sum(bws) / len(bws)
                    self._metric_values["bandwidth"].setText(f"{avg_bw:.2f}")
                    self._metric_footnotes["bandwidth"].setText("From last diagnostic")

                if jits:
                    avg_jit = sum(jits) / len(jits)
                    self._metric_values["jitter"].setText(f"{avg_jit:.1f}")
                    self._metric_footnotes["jitter"].setText("From last diagnostic")

            # Congestion score
            score = r["congestion_score"] or 0
            severity = r["severity"] or "NONE"
            self._gauge.set_score(score, severity)
            dominant = (r["dominant_signal"] or "").replace("_", " ").title()
            self._score_hint.setText(f"Severity: {severity}  •  Dominant: {dominant}")

            # ISP verdict
            p = theme_manager.palette
            isp_verdict = r["isp_verdict"] or "unknown"
            display_names = {
                "healthy": "Healthy",
                "local_congestion": "Local Congestion",
                "last_mile": "Last Mile Issue",
                "isp_degradation": "ISP Degradation",
                "isp_outage": "ISP Outage",
                "dns_issue": "DNS Issue",
            }
            display_text = display_names.get(isp_verdict, "Unknown")
            color = self._get_isp_color(p)
            self._isp_verdict_label.setText(display_text)
            self._isp_verdict_label.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {color};")
            self._isp_detail_label.setText("Based on last diagnostic run")

            # Recommendation
            algo = r["recommended_algo"]
            reason = r["recommendation_reason"] or ""

            if algo:
                a_color = self._get_algo_color(p)
                self._algo_label.setText(algo)
                self._algo_label.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {a_color};")
            else:
                self._algo_label.setText("No Algorithm Needed")
                self._algo_label.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {p.success};")

            self._reason_label.setText(reason)

        except Exception:
            pass

    def _go_to_diagnose(self):
        main_window = self.window()
        if main_window and hasattr(main_window, '_nav_buttons'):
            for btn in main_window._nav_buttons:
                if btn.text() == "Diagnose":
                    btn.click()
                    break