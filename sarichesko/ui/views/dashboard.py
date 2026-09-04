from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGraphicsOpacityEffect, QGridLayout, QScrollArea,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve

from ..widgets.congestion_gauge import CongestionGaugeWidget
from ...storage.db import get_connection, init_db
from ...storage.repository import Repository


def _stat_card(title: str, value: str, unit: str, color: str, footnote: str) -> tuple[QFrame, QLabel, QLabel]:
    card = QFrame()
    card.setObjectName("card")
    card.setMinimumHeight(105)
    cl = QVBoxLayout(card)
    cl.setContentsMargins(18, 14, 18, 14)
    cl.setSpacing(6)

    lbl_t = QLabel(title)
    lbl_t.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")

    val_row = QHBoxLayout()
    val_row.setSpacing(4)
    val_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBaseline)

    lbl_v = QLabel(value)
    lbl_v.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {color};")

    lbl_u = QLabel(unit)
    lbl_u.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {color}; padding-top: 8px;")

    val_row.addWidget(lbl_v)
    val_row.addWidget(lbl_u)

    lbl_f = QLabel(footnote)
    lbl_f.setStyleSheet("font-size: 11px; color: #475569;")

    cl.addWidget(lbl_t)
    cl.addLayout(val_row)
    cl.addWidget(lbl_f)
    return card, lbl_v, lbl_f


def _status_row(label: str, status: str, color: str) -> tuple[QHBoxLayout, QLabel]:
    row = QHBoxLayout()
    row.setSpacing(10)

    dot = QLabel("●")
    dot.setStyleSheet(f"font-size: 10px; color: {color};")
    dot.setFixedWidth(14)

    lbl = QLabel(label)
    lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #e2e8f0;")

    val = QLabel(status)
    val.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {color};")
    val.setAlignment(Qt.AlignmentFlag.AlignRight)

    row.addWidget(dot)
    row.addWidget(lbl)
    row.addStretch()
    row.addWidget(val)
    return row, val


class DashboardView(QWidget):
    def __init__(self):
        super().__init__()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #000000; border: none; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        # Header
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Dashboard")
        title.setStyleSheet("font-size: 26px; font-weight: 800; color: #ffffff;")
        subtitle = QLabel("Real-time network health overview")
        subtitle.setStyleSheet("font-size: 13px; color: #64748b;")
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
            ("LATENCY", "—", "ms", "#00f0ff", "No data yet"),
            ("PACKET LOSS", "—", "%", "#ef4444", "No data yet"),
            ("BANDWIDTH", "—", "Mbps", "#a78bfa", "No data yet"),
            ("JITTER", "—", "ms", "#f59e0b", "No data yet"),
        ]
        keys = ["latency", "packet_loss", "bandwidth", "jitter"]
        for i, (t, v, u, c, f) in enumerate(card_info):
            card, val_label, foot_label = _stat_card(t, v, u, c, f)
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
        st_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        sl.addWidget(st_title)

        self._status_values = {}
        statuses = [
            ("Monitor Engine", "Idle", "#64748b"),
            ("ISP Probe", "Ready", "#00e5a3"),
            ("Congestion Scorer", "Idle", "#64748b"),
            ("Traffic Controller", "Inactive", "#64748b"),
            ("Database", "Connected", "#00e5a3"),
        ]
        for lbl, val, col in statuses:
            row, val_lbl = _status_row(lbl, val, col)
            sl.addLayout(row)
            self._status_values[lbl] = val_lbl

        two_col.addWidget(status_card, 1)

        # Congestion Gauge
        gauge_card = QFrame()
        gauge_card.setObjectName("card")
        gl = QVBoxLayout(gauge_card)
        gl.setContentsMargins(20, 16, 20, 16)

        g_title = QLabel("CONGESTION SCORE")
        g_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        gl.addWidget(g_title)

        self._gauge = CongestionGaugeWidget()
        self._gauge.setMinimumSize(180, 180)
        gl.addWidget(self._gauge, 0, Qt.AlignmentFlag.AlignCenter)

        self._score_hint = QLabel("Run a diagnostic to generate a score")
        self._score_hint.setStyleSheet("font-size: 11px; color: #334155;")
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
        isp_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        il.addWidget(isp_title)

        self._isp_verdict_label = QLabel("Not tested")
        self._isp_verdict_label.setStyleSheet("font-size: 18px; font-weight: 700; color: #475569;")
        il.addWidget(self._isp_verdict_label)

        self._isp_detail_label = QLabel("Run a diagnostic to check ISP health")
        self._isp_detail_label.setStyleSheet("font-size: 12px; color: #475569;")
        self._isp_detail_label.setWordWrap(True)
        il.addWidget(self._isp_detail_label)

        self._isp_stats = QLabel("")
        self._isp_stats.setStyleSheet("font-size: 11px; color: #64748b;")
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
        rec_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        rl.addWidget(rec_title)

        self._algo_label = QLabel("Awaiting Diagnostic")
        self._algo_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #334155;")
        rl.addWidget(self._algo_label)

        self._reason_label = QLabel("Run a diagnostic to receive an algorithm recommendation")
        self._reason_label.setStyleSheet("font-size: 12px; color: #475569;")
        self._reason_label.setWordWrap(True)
        rl.addWidget(self._reason_label)

        self._algos_avail = QLabel("Available: Leaky Bucket · Token Bucket · RED · CoDel")
        self._algos_avail.setStyleSheet("font-size: 10px; color: #334155; letter-spacing: 0.3px;")
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

        # Load latest results from DB
        self._load_latest()

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
                conn.close()
                return

            r = runs[0]

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
            isp_verdict = r["isp_verdict"] or "unknown"
            verdict_display = {
                "healthy": ("Healthy", "#00e5a3"),
                "local_congestion": ("Local Congestion", "#f59e0b"),
                "last_mile": ("Last Mile Issue", "#ef4444"),
                "isp_degradation": ("ISP Degradation", "#f59e0b"),
                "isp_outage": ("ISP Outage", "#ef4444"),
                "dns_issue": ("DNS Issue", "#ef4444"),
            }
            display_text, color = verdict_display.get(isp_verdict, ("Unknown", "#64748b"))
            self._isp_verdict_label.setText(display_text)
            self._isp_verdict_label.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {color};")
            self._isp_detail_label.setText("Based on last diagnostic run")

            # Recommendation
            algo = r["recommended_algo"]
            reason = r["recommendation_reason"] or ""
            confidence = r["confidence"] or ""

            algo_colors = {
                "Leaky Bucket": "#00f0ff",
                "Token Bucket": "#a78bfa",
                "RED": "#f59e0b",
                "CoDel": "#00e5a3",
            }

            if algo:
                a_color = algo_colors.get(algo, "#00f0ff")
                self._algo_label.setText(algo)
                self._algo_label.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {a_color};")
            else:
                self._algo_label.setText("No Algorithm Needed")
                self._algo_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #00e5a3;")

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