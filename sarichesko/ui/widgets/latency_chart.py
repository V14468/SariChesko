from typing import Optional, Union, Callable
from collections import deque
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QLinearGradient, QBrush, QFont

from ..theme import theme_manager, Palette, DARK


class LatencyChartWidget(QWidget):
    """Real-time scrolling line chart for latency, loss, jitter, or bandwidth."""

    def __init__(self, title: str = "Latency", unit: str = "ms",
                 color_token: Union[str, Callable[[Palette], str]] = "accent",
                 max_points: int = 120, parent=None):
        super().__init__(parent)
        self._title = title
        self._unit = unit
        self._color_token = color_token
        self._max_points = max_points
        self._data: deque[Optional[float]] = deque(maxlen=max_points)
        self._min_val = 0.0
        self._max_val = 1.0
        self.setMinimumHeight(160)
        theme_manager.changed.connect(lambda _: self.update())

    def _resolve_color(self, p: Palette) -> QColor:
        if callable(self._color_token):
            return QColor(self._color_token(p))
        if hasattr(p, self._color_token):
            return QColor(getattr(p, self._color_token))
        # Backward-compatibility fallback for legacy hex strings
        legacy_map = {
            DARK.accent: p.accent,
            DARK.purple: p.purple,
            DARK.warning: p.warning,
            DARK.danger: p.danger,
            DARK.success: p.success,
        }
        if self._color_token in legacy_map:
            return QColor(legacy_map[self._color_token])
        return QColor(self._color_token)

    def add_value(self, value: Optional[float]):
        self._data.append(value)
        valid = [v for v in self._data if v is not None]
        if valid:
            self._min_val = max(0.0, min(valid) - 5)
            self._max_val = max(valid) + 5
            if self._max_val <= self._min_val:
                self._max_val = self._min_val + 10
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            palette = theme_manager.palette

            w, h = self.width(), self.height()
            margin_top = 30
            margin_bottom = 20
            margin_left = 50
            margin_right = 16
            chart_w = w - margin_left - margin_right
            chart_h = h - margin_top - margin_bottom

            # Background
            p.fillRect(self.rect(), QColor(palette.surface_alt))

            # Chart area border
            p.setPen(QPen(QColor(palette.chart_grid), 1))
            p.drawRect(margin_left, margin_top, chart_w, chart_h)

            # Title
            p.setPen(QColor(palette.text_muted))
            font = QFont("Segoe UI", 10, QFont.Weight.Bold)
            p.setFont(font)
            p.drawText(margin_left, 18, f"{self._title} ({self._unit})")

            # Series color
            series_color = self._resolve_color(palette)

            # Current value
            if self._data:
                cur = self._data[-1]
                p.setPen(series_color)
                font_val = QFont("Segoe UI", 10, QFont.Weight.Bold)
                p.setFont(font_val)
                if cur is not None:
                    p.drawText(w - margin_right - 80, 18, f"{cur:.1f} {self._unit}")
                else:
                    p.drawText(w - margin_right - 80, 18, f"— {self._unit}")

            valid_count = sum(1 for v in self._data if v is not None)
            if valid_count < 2:
                p.setPen(QColor(palette.text_faint))
                p.setFont(QFont("Segoe UI", 9))
                p.drawText(margin_left, margin_top, chart_w, chart_h,
                           Qt.AlignmentFlag.AlignCenter, "Waiting for data...")
                return

            # Grid lines
            p.setPen(QPen(QColor(palette.chart_grid), 0.5))
            grid_count = 4
            for i in range(1, grid_count):
                gy = margin_top + (chart_h / grid_count) * i
                p.drawLine(margin_left, int(gy), margin_left + chart_w, int(gy))

                val = self._max_val - (self._max_val - self._min_val) * (i / grid_count)
                p.setPen(QColor(palette.text_faint))
                p.setFont(QFont("Segoe UI", 8))
                p.drawText(4, int(gy) + 4, f"{val:.0f}")
                p.setPen(QPen(QColor(palette.chart_grid), 0.5))

            # Build line path
            data = list(self._data)
            n = len(data)
            step_x = chart_w / (self._max_points - 1) if self._max_points > 1 else chart_w
            val_range = self._max_val - self._min_val
            if val_range <= 0:
                val_range = 1.0

            line = QPainterPath()
            fill = QPainterPath()
            in_segment = False
            last_valid_x = None

            for i, val in enumerate(data):
                x = margin_left + (self._max_points - n + i) * step_x
                if val is None:
                    if in_segment and last_valid_x is not None:
                        fill.lineTo(last_valid_x, margin_top + chart_h)
                        in_segment = False
                    continue

                y = margin_top + chart_h - ((val - self._min_val) / val_range) * chart_h
                y = max(margin_top, min(margin_top + chart_h, y))

                if not in_segment:
                    line.moveTo(x, y)
                    fill.moveTo(x, margin_top + chart_h)
                    fill.lineTo(x, y)
                    in_segment = True
                else:
                    line.lineTo(x, y)
                    fill.lineTo(x, y)
                last_valid_x = x

            if in_segment and last_valid_x is not None:
                fill.lineTo(last_valid_x, margin_top + chart_h)
                fill.closeSubpath()

            # Fill gradient under line
            grad = QLinearGradient(0, margin_top, 0, margin_top + chart_h)
            fill_color = QColor(series_color)
            fill_color.setAlpha(40)
            grad.setColorAt(0.0, fill_color)
            fill_color.setAlpha(0)
            grad.setColorAt(1.0, fill_color)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(grad))
            p.drawPath(fill)

            # Draw line
            p.setPen(QPen(series_color, 1.8))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(line)
        finally:
            p.end()