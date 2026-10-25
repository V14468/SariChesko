from typing import Union, Callable
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics

from ..theme import theme_manager, Palette, DARK


def _resolve_color(color_src: Union[str, Callable[[Palette], str]], p: Palette) -> QColor:
    if callable(color_src):
        return QColor(color_src(p))
    if hasattr(p, color_src):
        return QColor(getattr(p, color_src))
    legacy = {
        DARK.accent: p.accent,
        DARK.purple: p.purple,
        DARK.warning: p.warning,
        DARK.success: p.success,
        DARK.danger: p.danger,
    }
    return QColor(legacy.get(color_src, color_src))


class AlgoBarChartWidget(QWidget):
    """Small-multiple bar chart comparing a single metric across algorithms.

    Each metric (throughput, latency, loss, fairness) gets its own instance
    so bars are always normalized within a single, comparable unit -- avoids
    putting Mbps and % on the same axis.
    """

    def __init__(self, title: str = "", unit: str = "", higher_is_better: bool = True, parent=None):
        super().__init__(parent)
        self._title = title
        self._unit = unit
        self._higher_is_better = higher_is_better
        self._entries: list[tuple[str, float, Union[str, Callable[[Palette], str]]]] = []
        self.setMinimumHeight(190)
        self.setMinimumWidth(160)
        theme_manager.changed.connect(lambda _: self.update())

    def set_data(self, entries: list[tuple[str, float, Union[str, Callable[[Palette], str]]]]):
        self._entries = entries
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            palette = theme_manager.palette

            w, h = self.width(), self.height()
            p.fillRect(self.rect(), QColor(palette.surface_alt))

            margin_bottom = 38
            margin_side = 12

            title_font = QFont("Segoe UI", 10, QFont.Weight.Bold)
            hint_font = QFont("Segoe UI", 8)
            title_fm = QFontMetrics(title_font)
            hint_fm = QFontMetrics(hint_font)

            top_pad = 6
            title_baseline_y = top_pad + title_fm.ascent()
            hint_baseline_y = title_baseline_y + title_fm.descent() + 2 + hint_fm.ascent()
            margin_top = hint_baseline_y + hint_fm.descent() + 8

            p.setPen(QColor(palette.text_secondary))
            p.setFont(title_font)
            title_text = f"{self._title} ({self._unit})" if self._unit else self._title
            available_w = w - margin_side * 2
            elided_title = title_fm.elidedText(title_text, Qt.TextElideMode.ElideRight, available_w)
            p.drawText(margin_side, title_baseline_y, elided_title)

            p.setPen(QColor(palette.text_faint))
            p.setFont(hint_font)
            hint = "higher is better" if self._higher_is_better else "lower is better"
            p.drawText(margin_side, hint_baseline_y, hint)

            if not self._entries:
                p.setPen(QColor(palette.text_faint))
                p.setFont(QFont("Segoe UI", 9))
                p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data yet")
                return

            chart_top = margin_top
            chart_bottom = h - margin_bottom
            chart_h = max(10, chart_bottom - chart_top)
            chart_w = w - margin_side * 2

            max_val = max((v for _, v, _ in self._entries), default=1.0)
            if max_val <= 0:
                max_val = 1.0

            n = len(self._entries)
            gap = 12
            bar_w = max(1.0, (chart_w - gap * (n - 1)) / n) if n else chart_w

            p.setPen(QPen(QColor(palette.chart_grid), 1))
            p.drawLine(margin_side, chart_bottom, margin_side + chart_w, chart_bottom)

            if self._higher_is_better:
                best_idx = max(range(n), key=lambda i: self._entries[i][1])
            else:
                best_idx = min(range(n), key=lambda i: self._entries[i][1])

            for i, (label, value, color_source) in enumerate(self._entries):
                x = margin_side + i * (bar_w + gap)
                bar_h = (value / max_val) * (chart_h - 22) if max_val > 0 else 0
                y = chart_bottom - bar_h

                color = _resolve_color(color_source, palette)
                if i != best_idx:
                    color.setAlpha(130)

                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(color)
                p.drawRoundedRect(int(x), int(y), int(bar_w), int(bar_h), 4, 4)

                p.setPen(QColor(palette.text_strong) if i == best_idx else QColor(palette.text_secondary))
                p.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
                p.drawText(int(x) - 6, int(y) - 16, int(bar_w) + 12, 14,
                           Qt.AlignmentFlag.AlignCenter, f"{value:.2f}")

                p.setPen(QColor(palette.text_secondary))
                p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                short = label.replace("Bucket", "").strip()
                p.drawText(int(x) - 6, chart_bottom + 6, int(bar_w) + 12, 14,
                           Qt.AlignmentFlag.AlignCenter, short)

                if i == best_idx:
                    p.setPen(QColor(palette.star))
                    p.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
                    p.drawText(int(x) - 6, chart_bottom + 20, int(bar_w) + 12, 14,
                               Qt.AlignmentFlag.AlignCenter, "\u2605 best")
        finally:
            p.end()