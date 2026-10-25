from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QBrush

from ..theme import theme_manager, Palette


class CongestionGaugeWidget(QWidget):
    """Arc gauge displaying the congestion score 0–100."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._score = 0.0
        self._severity = "NONE"
        self.setMinimumSize(180, 180)
        theme_manager.changed.connect(lambda _: self.update())

    def set_score(self, score: float, severity: str):
        self._score = score
        self._severity = severity
        self.update()

    def _score_color(self, p: Palette) -> QColor:
        if self._score < 20:
            return QColor(p.success)
        elif self._score < 40:
            return QColor(p.accent)
        elif self._score < 65:
            return QColor(p.warning)
        elif self._score < 85:
            return QColor(p.orange)
        else:
            return QColor(p.danger)

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            palette = theme_manager.palette

            w, h = self.width(), self.height()
            cx, cy = w / 2, h / 2
            radius = min(w, h) / 2 - 20

            # Background arc (track)
            start_angle = 225
            span_angle = -270

            p.setPen(QPen(QColor(palette.chart_grid), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(
                int(cx - radius), int(cy - radius),
                int(radius * 2), int(radius * 2),
                start_angle * 16, span_angle * 16,
            )

            # Filled arc (score)
            if self._score > 0:
                fill_span = span_angle * (self._score / 100)
                color = self._score_color(palette)
                p.setPen(QPen(color, 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                p.drawArc(
                    int(cx - radius), int(cy - radius),
                    int(radius * 2), int(radius * 2),
                    start_angle * 16, int(fill_span * 16),
                )

            # Score number
            p.setPen(self._score_color(palette) if self._score > 0 else QColor(palette.text_faint))
            font = QFont("Segoe UI", 32, QFont.Weight.Bold)
            p.setFont(font)
            score_text = f"{self._score:.0f}" if self._score > 0 else "—"
            p.drawText(0, 0, w, h - 10, Qt.AlignmentFlag.AlignCenter, score_text)

            # Severity label — map internal "NONE" to user-facing "HEALTHY"
            display_severity = "HEALTHY" if self._severity == "NONE" else self._severity
            severity_color = self._score_color(palette)
            small_font = QFont("Segoe UI", 10, QFont.Weight.DemiBold)
            p.setFont(small_font)

            # Measure text to center dot + label as a unit
            fm = p.fontMetrics()
            label_w = fm.horizontalAdvance(display_severity)
            label_h = fm.height()
            dot_d = 8  # dot diameter
            gap = 6    # space between dot and text
            total_w = dot_d + gap + label_w

            # Position: centered horizontally, below the score number
            base_x = int(cx - total_w / 2)
            base_y = int(cy + radius * 0.45)

            # Dot
            dot_y = int(base_y + (label_h - dot_d) / 2)
            p.setBrush(QBrush(severity_color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(base_x, dot_y, dot_d, dot_d)

            # Text
            p.setPen(severity_color)
            p.drawText(base_x + dot_d + gap, base_y, label_w, label_h,
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                       display_severity)
        finally:
            p.end()