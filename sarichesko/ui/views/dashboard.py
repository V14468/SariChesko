from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGraphicsOpacityEffect, QGridLayout, QScrollArea,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve


def _card(title: str, value: str, unit: str, color: str, footnote: str) -> QFrame:
    """Reusable metric card widget."""
    card = QFrame()
    card.setObjectName("card")
    card.setMinimumHeight(110)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(6)

    lbl_title = QLabel(title)
    lbl_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")

    val_row = QHBoxLayout()
    val_row.setSpacing(4)
    val_row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBaseline)

    lbl_val = QLabel(value)
    lbl_val.setStyleSheet(f"font-size: 28px; font-weight: 800; color: {color};")

    lbl_unit = QLabel(unit)
    lbl_unit.setStyleSheet(f"font-size: 13px; font-weight: 600; color: {color}; padding-top: 8px;")

    val_row.addWidget(lbl_val)
    val_row.addWidget(lbl_unit)

    lbl_foot = QLabel(footnote)
    lbl_foot.setStyleSheet("font-size: 11px; color: #475569;")

    layout.addWidget(lbl_title)
    layout.addLayout(val_row)
    layout.addWidget(lbl_foot)
    return card


def _status_row(label: str, status: str, color: str) -> QHBoxLayout:
    """Single status indicator row."""
    row = QHBoxLayout()
    row.setSpacing(10)

    dot = QLabel("●")
    dot.setStyleSheet(f"font-size: 10px; color: {color}; padding: 0;")
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
    return row


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
        layout.setSpacing(20)

        # ── Header ──
        header = QHBoxLayout()
        header.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        title = QLabel("Dashboard")
        title.setStyleSheet("font-size: 26px; font-weight: 800; color: #ffffff; letter-spacing: 0.5px;")

        subtitle = QLabel("Real-time network health overview")
        subtitle.setStyleSheet("font-size: 13px; font-weight: 500; color: #64748b;")

        title_col.addWidget(title)
        title_col.addWidget(subtitle)

        header.addLayout(title_col)
        header.addStretch()

        btn_diag = QPushButton("Run Diagnostic")
        btn_diag.setObjectName("primary_btn")
        btn_diag.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_diag.setFixedHeight(38)
        header.addWidget(btn_diag)

        layout.addLayout(header)

        # ── Metric Cards Row ──
        cards_grid = QGridLayout()
        cards_grid.setSpacing(14)

        cards_grid.addWidget(
            _card("LATENCY", "—", "ms", "#00f0ff", "Baseline not established"),
            0, 0
        )
        cards_grid.addWidget(
            _card("PACKET LOSS", "—", "%", "#00e5a3", "Waiting for measurement"),
            0, 1
        )
        cards_grid.addWidget(
            _card("BANDWIDTH", "—", "Mbps", "#a78bfa", "No active session"),
            0, 2
        )
        cards_grid.addWidget(
            _card("JITTER", "—", "ms", "#f59e0b", "Waiting for measurement"),
            0, 3
        )

        layout.addLayout(cards_grid)

        # ── Two-Column: System Status + Congestion Score ──
        two_col = QHBoxLayout()
        two_col.setSpacing(14)

        # Left: System Status Panel
        status_card = QFrame()
        status_card.setObjectName("card")
        status_layout = QVBoxLayout(status_card)
        status_layout.setContentsMargins(20, 18, 20, 18)
        status_layout.setSpacing(14)

        status_title = QLabel("SYSTEM STATUS")
        status_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        status_layout.addWidget(status_title)

        statuses = [
            ("Monitor Engine", "Idle", "#64748b"),
            ("ISP Probe", "Ready", "#00e5a3"),
            ("Congestion Scorer", "Idle", "#64748b"),
            ("Traffic Controller", "Inactive", "#64748b"),
            ("Database", "Connected", "#00e5a3"),
        ]
        for lbl, val, col in statuses:
            status_layout.addLayout(_status_row(lbl, val, col))

        two_col.addWidget(status_card, 1)

        # Right: Congestion Score Panel
        score_card = QFrame()
        score_card.setObjectName("card")
        score_layout = QVBoxLayout(score_card)
        score_layout.setContentsMargins(20, 18, 20, 18)
        score_layout.setSpacing(10)

        score_title = QLabel("CONGESTION SCORE")
        score_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        score_layout.addWidget(score_title)

        score_val = QLabel("—")
        score_val.setStyleSheet("font-size: 56px; font-weight: 800; color: #64748b;")
        score_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_layout.addWidget(score_val)

        score_label = QLabel("No data yet")
        score_label.setStyleSheet("font-size: 13px; font-weight: 600; color: #475569;")
        score_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_layout.addWidget(score_label)

        score_hint = QLabel("Start a monitoring session to generate\na real-time congestion score (0–100)")
        score_hint.setStyleSheet("font-size: 11px; color: #334155;")
        score_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        score_layout.addWidget(score_hint)
        score_layout.addStretch()

        two_col.addWidget(score_card, 1)

        layout.addLayout(two_col)

        # ── ISP & Algorithm Status Row ──
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(14)

        # ISP Health
        isp_card = QFrame()
        isp_card.setObjectName("card")
        isp_layout = QVBoxLayout(isp_card)
        isp_layout.setContentsMargins(20, 18, 20, 18)
        isp_layout.setSpacing(10)

        isp_title = QLabel("ISP HEALTH")
        isp_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        isp_layout.addWidget(isp_title)

        isp_probes = [
            ("Gateway", "Not tested", "#475569"),
            ("ISP First Hop", "Not tested", "#475569"),
            ("WAN (8.8.8.8)", "Not tested", "#475569"),
            ("DNS Resolution", "Not tested", "#475569"),
        ]
        for lbl, val, col in isp_probes:
            isp_layout.addLayout(_status_row(lbl, val, col))

        isp_layout.addStretch()
        bottom_row.addWidget(isp_card, 1)

        # Active Algorithm
        algo_card = QFrame()
        algo_card.setObjectName("card")
        algo_layout = QVBoxLayout(algo_card)
        algo_layout.setContentsMargins(20, 18, 20, 18)
        algo_layout.setSpacing(10)

        algo_title = QLabel("ACTIVE ALGORITHM")
        algo_title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        algo_layout.addWidget(algo_title)

        algo_none = QLabel("None Applied")
        algo_none.setStyleSheet("font-size: 22px; font-weight: 700; color: #334155;")
        algo_none.setAlignment(Qt.AlignmentFlag.AlignCenter)
        algo_layout.addWidget(algo_none)

        algo_hint = QLabel("Run a diagnostic to receive an\nalgorithm recommendation")
        algo_hint.setStyleSheet("font-size: 12px; color: #475569;")
        algo_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        algo_layout.addWidget(algo_hint)

        algos_available = QLabel("Available: Leaky Bucket · Token Bucket · RED · CoDel")
        algos_available.setStyleSheet("font-size: 10px; color: #334155; letter-spacing: 0.3px;")
        algos_available.setAlignment(Qt.AlignmentFlag.AlignCenter)
        algo_layout.addWidget(algos_available)
        algo_layout.addStretch()

        bottom_row.addWidget(algo_card, 1)

        layout.addLayout(bottom_row)
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