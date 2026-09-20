from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt

from ...core.recommendation_engine import Algorithm


ALGO_COLORS = {
    Algorithm.LEAKY_BUCKET: "#00f0ff",
    Algorithm.TOKEN_BUCKET: "#a78bfa",
    Algorithm.RED: "#f59e0b",
    Algorithm.CODEL: "#00e5a3",
}

# How each recommendation's `parameters` dict should be shown to a human,
# in the order that reads most naturally for that algorithm.
PARAM_LABELS = {
    Algorithm.LEAKY_BUCKET: [("rate_bps", "Rate", lambda v: f"{v / 1_000_000:.1f} Mbps"),
                             ("burst_bytes", "Burst", lambda v: f"{v} B")],
    Algorithm.TOKEN_BUCKET: [("rate_bps", "Rate", lambda v: f"{v / 1_000_000:.1f} Mbps"),
                             ("burst_bytes", "Burst", lambda v: f"{v} B"),
                             ("latency_ms", "Max latency", lambda v: f"{v} ms")],
    Algorithm.RED: [("min_th", "Min threshold", lambda v: str(v)),
                    ("max_th", "Max threshold", lambda v: str(v)),
                    ("max_p", "Drop probability", lambda v: f"{v:.0%}"),
                    ("limit", "Queue limit", lambda v: str(v))],
    Algorithm.CODEL: [("target_ms", "Target delay", lambda v: f"{v} ms"),
                      ("interval_ms", "Interval", lambda v: f"{v} ms"),
                      ("limit", "Queue limit", lambda v: f"{v} packets")],
}


class PermissionDialog(QDialog):
    """Human-in-the-loop confirmation before SariChesko changes any network
    setting. SariChesko never applies a fix without this dialog being shown
    and explicitly accepted first -- there is no "always apply" or
    auto-apply path anywhere in the app.
    """

    def __init__(self, iface: str, algo: Algorithm, parameters: dict, reason: str,
                 congestion_score: float, severity: str, supported: bool,
                 requires_elevation: bool, unsupported_message: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Apply Recommended Fix?")
        self.setMinimumWidth(440)
        self.setStyleSheet("""
            QDialog { background-color: #0a0b10; }
            QLabel { color: #e2e8f0; }
        """)

        color = ALGO_COLORS.get(algo, "#00f0ff")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        # Header: severity + score
        header = QHBoxLayout()
        sev_colors = {"CRITICAL": "#ef4444", "HIGH": "#ef4444", "MEDIUM": "#f59e0b", "LOW": "#f59e0b", "NONE": "#00e5a3"}
        dot = QLabel("\u25cf")
        dot.setStyleSheet(f"font-size: 14px; color: {sev_colors.get(severity, '#f59e0b')};")
        header.addWidget(dot)
        header_lbl = QLabel(f"Congestion detected \u2014 severity {severity} (score {congestion_score:.0f}/100)")
        header_lbl.setStyleSheet("font-size: 13px; font-weight: 700; color: #e2e8f0;")
        header.addWidget(header_lbl)
        header.addStretch()
        layout.addLayout(header)

        # Algorithm card
        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(8)

        rec_title = QLabel("RECOMMENDED APPROACH")
        rec_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        cl.addWidget(rec_title)

        algo_lbl = QLabel(algo.value)
        algo_lbl.setStyleSheet(f"font-size: 22px; font-weight: 800; color: {color};")
        cl.addWidget(algo_lbl)

        reason_lbl = QLabel(reason)
        reason_lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
        reason_lbl.setWordWrap(True)
        cl.addWidget(reason_lbl)

        if supported:
            params_lbl = QLabel(self._format_params(algo, parameters))
            params_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
            params_lbl.setWordWrap(True)
            cl.addWidget(params_lbl)

        layout.addWidget(card)

        if not supported:
            # Honest, explicit "unavailable on this OS" state -- never silently
            # skipped and never pretended to be applied.
            warn = QFrame()
            warn.setObjectName("card")
            wl = QVBoxLayout(warn)
            wl.setContentsMargins(16, 12, 16, 12)
            wl.setSpacing(4)
            warn_title = QLabel("\u26a0 Not available on this operating system")
            warn_title.setStyleSheet("font-size: 12px; font-weight: 700; color: #f59e0b;")
            wl.addWidget(warn_title)
            warn_body = QLabel(unsupported_message or
                                f"{algo.value} cannot be applied for real on this OS.")
            warn_body.setStyleSheet("font-size: 11px; color: #94a3b8;")
            warn_body.setWordWrap(True)
            wl.addWidget(warn_body)
            layout.addWidget(warn)
        elif requires_elevation:
            note = QLabel(
                "\u2139 This changes your system's network configuration and requires "
                "Administrator/root privileges. If SariChesko isn't running with those "
                "privileges, this step will fail with a clear message and nothing will change."
            )
            note.setStyleSheet("font-size: 10px; color: #475569; font-style: italic;")
            note.setWordWrap(True)
            layout.addWidget(note)

        iface_lbl = QLabel(f"Target interface: {iface}")
        iface_lbl.setStyleSheet("font-size: 11px; color: #64748b;")
        layout.addWidget(iface_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        if supported:
            self._btn_cancel = QPushButton("Cancel")
            self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_cancel.setFixedHeight(36)
            self._btn_cancel.clicked.connect(self.reject)
            btn_row.addWidget(self._btn_cancel)

            self._btn_apply = QPushButton(f"Apply {algo.value}")
            self._btn_apply.setObjectName("primary_btn")
            self._btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_apply.setFixedHeight(36)
            self._btn_apply.clicked.connect(self.accept)
            btn_row.addWidget(self._btn_apply)
        else:
            self._btn_close = QPushButton("Close")
            self._btn_close.setObjectName("primary_btn")
            self._btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_close.setFixedHeight(36)
            self._btn_close.clicked.connect(self.reject)
            btn_row.addWidget(self._btn_close)

        layout.addLayout(btn_row)

    @staticmethod
    def _format_params(algo: Algorithm, parameters: dict) -> str:
        labels = PARAM_LABELS.get(algo, [])
        parts = []
        for key, label, fmt in labels:
            if key in parameters:
                try:
                    parts.append(f"{label}: {fmt(parameters[key])}")
                except Exception:
                    parts.append(f"{label}: {parameters[key]}")
        return "  \u00b7  ".join(parts)