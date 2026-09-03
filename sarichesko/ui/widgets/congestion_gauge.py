import math
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QConicalGradient, QBrush


class CongestionGaugeWidget(QWidget):
    """Arc gauge displaying the congestion score 0–100."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._score = 0.0
        self._severity = "NONE"
        self.setMinimumSize(180, 180)

    def set_score(self, score: float, severity: str):
        self._score = score
        self._severity = severity
        self.update()

    def _score_color(self) -> QColor:
        if self._score < 20:
            return QColor("#00e5a3")
        elif self._score < 40:
            return QColor("#00f0ff")
        elif self._score < 65:
            return QColor("#f59e0b")
        elif self._score < 85:
            return QColor("#f97316")
        else:
            return QColor("#ef4444")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        radius = min(w, h) / 2 - 20

        # Background arc (track)
        start_angle = 225
        span_angle = -270

        p.setPen(QPen(QColor(20, 24, 40), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(
            int(cx - radius), int(cy - radius),
            int(radius * 2), int(radius * 2),
            start_angle * 16, span_angle * 16,
        )

        # Filled arc (score)
        if self._score > 0:
            fill_span = span_angle * (self._score / 100)
            color = self._score_color()
            p.setPen(QPen(color, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(
                int(cx - radius), int(cy - radius),
                int(radius * 2), int(radius * 2),
                start_angle * 16, int(fill_span * 16),
            )

        # Score number
        p.setPen(self._score_color() if self._score > 0 else QColor(71, 85, 105))
        font = QFont("Segoe UI", 32, QFont.Weight.Bold)
        p.setFont(font)
        score_text = f"{self._score:.0f}" if self._score > 0 else "—"
        p.drawText(0, 0, w, h - 10, Qt.AlignmentFlag.AlignCenter, score_text)

        # Severity label
        p.setPen(QColor(100, 116, 139))
        small_font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
        p.setFont(small_font)
        p.drawText(0, int(cy + 28), w, 20, Qt.AlignmentFlag.AlignCenter, self._severity)

        p.end()