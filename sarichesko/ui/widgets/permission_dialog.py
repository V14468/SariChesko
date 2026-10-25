from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt

from ...core.recommendation_engine import Algorithm
from ..theme import Palette, style


def algo_colors(p: Palette) -> dict:
    return {
        Algorithm.LEAKY_BUCKET: p.accent,
        Algorithm.TOKEN_BUCKET: p.purple,
        Algorithm.RED: p.warning,
        Algorithm.CODEL: p.success,
    }


def severity_colors(p: Palette) -> dict:
    return {
        "CRITICAL": p.danger,
        "HIGH": p.danger,
        "MEDIUM": p.warning,
        "LOW": p.warning,
        "NONE": p.success,
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
        style(self, lambda p: f"""
            QDialog {{ background-color: {p.surface_raised}; }}
            QLabel {{ color: {p.text}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        # Header: severity + score
        header = QHBoxLayout()
        dot = QLabel("\u25cf")
        style(dot, lambda p: f"font-size: 14px; color: {severity_colors(p).get(severity, p.warning)};")
        header.addWidget(dot)
        header_lbl = QLabel(f"Congestion detected \u2014 severity {severity} (score {congestion_score:.0f}/100)")
        style(header_lbl, lambda p: f"font-size: 13px; font-weight: 700; color: {p.text};")
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
        style(rec_title, lambda p: f"font-size: 10px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")
        cl.addWidget(rec_title)

        algo_lbl = QLabel(algo.value)
        style(algo_lbl, lambda p: f"font-size: 22px; font-weight: 800; color: {algo_colors(p).get(algo, p.accent)};")
        cl.addWidget(algo_lbl)

        reason_lbl = QLabel(reason)
        style(reason_lbl, lambda p: f"font-size: 12px; color: {p.text_secondary};")
        reason_lbl.setWordWrap(True)
        cl.addWidget(reason_lbl)

        if supported:
            params_lbl = QLabel(self._format_params(algo, parameters))
            style(params_lbl, lambda p: f"font-size: 11px; color: {p.text_muted};")
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
            style(warn_title, lambda p: f"font-size: 12px; font-weight: 700; color: {p.warning};")
            wl.addWidget(warn_title)
            warn_body = QLabel(unsupported_message or
                                f"{algo.value} cannot be applied for real on this OS.")
            style(warn_body, lambda p: f"font-size: 11px; color: {p.text_secondary};")
            warn_body.setWordWrap(True)
            wl.addWidget(warn_body)
            layout.addWidget(warn)
        elif requires_elevation:
            note = QLabel(
                "\u2139 This changes your system's network configuration and requires "
                "Administrator/root privileges. If SariChesko isn't running with those "
                "privileges, this step will fail with a clear message and nothing will change."
            )
            style(note, lambda p: f"font-size: 10px; color: {p.text_faint}; font-style: italic;")
            note.setWordWrap(True)
            layout.addWidget(note)

        iface_lbl = QLabel(f"Target interface: {iface}")
        style(iface_lbl, lambda p: f"font-size: 11px; color: {p.text_muted};")
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
        return "  ·  ".join(parts) if parts else "Default parameters"