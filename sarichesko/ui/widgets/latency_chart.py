from collections import deque
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QLinearGradient, QBrush, QFont


class LatencyChartWidget(QWidget):
    """Real-time scrolling line chart for latency, loss, jitter, or bandwidth."""

    def __init__(self, title: str = "Latency", unit: str = "ms",
                 color: str = "#00f0ff", max_points: int = 120, parent=None):
        super().__init__(parent)
        self._title = title
        self._unit = unit
        self._color = QColor(color)
        self._max_points = max_points
        self._data: deque[float] = deque(maxlen=max_points)
        self._min_val = 0.0
        self._max_val = 1.0
        self.setMinimumHeight(160)

    def add_value(self, value: float):
        self._data.append(value)
        if self._data:
            vals = list(self._data)
            self._min_val = max(0, min(vals) - 5)
            self._max_val = max(vals) + 5
            if self._max_val <= self._min_val:
                self._max_val = self._min_val + 10
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        margin_top = 30
        margin_bottom = 20
        margin_left = 50
        margin_right = 16
        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        # Background
        p.fillRect(self.rect(), QColor(5, 6, 10))

        # Chart area border
        p.setPen(QPen(QColor(20, 24, 40), 1))
        p.drawRect(margin_left, margin_top, chart_w, chart_h)

        # Title
        p.setPen(QColor(100, 116, 139))
        font = QFont("Segoe UI", 10, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(margin_left, 18, f"{self._title} ({self._unit})")

        # Current value
        if self._data:
            cur = self._data[-1]
            p.setPen(self._color)
            font_val = QFont("Segoe UI", 10, QFont.Weight.Bold)
            p.setFont(font_val)
            p.drawText(w - margin_right - 80, 18, f"{cur:.1f} {self._unit}")

        if len(self._data) < 2:
            p.setPen(QColor(71, 85, 105))
            p.setFont(QFont("Segoe UI", 9))
            p.drawText(margin_left, margin_top, chart_w, chart_h,
                       Qt.AlignmentFlag.AlignCenter, "Waiting for data...")
            p.end()
            return

        # Grid lines
        p.setPen(QPen(QColor(20, 24, 40), 0.5))
        grid_count = 4
        for i in range(1, grid_count):
            gy = margin_top + (chart_h / grid_count) * i
            p.drawLine(margin_left, int(gy), margin_left + chart_w, int(gy))

            val = self._max_val - (self._max_val - self._min_val) * (i / grid_count)
            p.setPen(QColor(71, 85, 105))
            p.setFont(QFont("Segoe UI", 8))
            p.drawText(4, int(gy) + 4, f"{val:.0f}")
            p.setPen(QPen(QColor(20, 24, 40), 0.5))

        # Build line path
        data = list(self._data)
        n = len(data)
        step_x = chart_w / (self._max_points - 1) if self._max_points > 1 else chart_w
        val_range = self._max_val - self._min_val

        line = QPainterPath()
        fill = QPainterPath()

        for i, val in enumerate(data):
            x = margin_left + (self._max_points - n + i) * step_x
            y = margin_top + chart_h - ((val - self._min_val) / val_range) * chart_h
            y = max(margin_top, min(margin_top + chart_h, y))
            if i == 0:
                line.moveTo(x, y)
                fill.moveTo(x, margin_top + chart_h)
                fill.lineTo(x, y)
            else:
                line.lineTo(x, y)
                fill.lineTo(x, y)

        # Fill gradient under line
        last_x = margin_left + (self._max_points - 1) * step_x
        fill.lineTo(last_x, margin_top + chart_h)
        fill.closeSubpath()

        grad = QLinearGradient(0, margin_top, 0, margin_top + chart_h)
        fill_color = QColor(self._color)
        fill_color.setAlpha(40)
        grad.setColorAt(0.0, fill_color)
        fill_color.setAlpha(0)
        grad.setColorAt(1.0, fill_color)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(fill)

        # Draw line
        p.setPen(QPen(self._color, 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(line)

        p.end()