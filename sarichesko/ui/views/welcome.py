import math
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath, QPixmap, QImage

from ..theme import theme_manager, derive_light_logo, style

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_raw_welcome_image: Optional[QImage] = None


def _get_raw_image() -> QImage:
    global _raw_welcome_image
    if _raw_welcome_image is None:
        _raw_welcome_image = QImage(str(_ASSETS_DIR / "sarichesko_welcome.png"))
    return _raw_welcome_image


class SCMonogramWidget(QWidget):
    """Minimalist SC monogram logo — geometric interlocking S and C letterforms."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(220, 220)
        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)  # ~25 fps, gentle

    def _tick(self):
        self._phase = (self._phase + 0.025) % (2 * math.pi)
        self.update()

    @staticmethod
    def draw_monogram(p: QPainter, cx: float, cy: float, size: float,
                      stroke_color: QColor, border_alpha: int = 30):
        """Draw the SC monogram at given center and size.

        Reusable by both the welcome-screen widget and the app icon painter.
        ``size`` is the full width/height of the bounding area.
        """
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── Rounded-rect container border ──
        margin = size * 0.06
        rect = QRectF(cx - size / 2 + margin, cy - size / 2 + margin,
                      size - 2 * margin, size - 2 * margin)
        corner = size * 0.18
        p.setPen(QPen(QColor(stroke_color.red(), stroke_color.green(),
                             stroke_color.blue(), border_alpha), size * 0.012))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, corner, corner)

        # ── Proportions for the letterforms ──
        stroke_w = size * 0.055          # uniform stroke weight
        inset = size * 0.20             # padding inside the container
        left = cx - size / 2 + inset
        right = cx + size / 2 - inset
        top = cy - size / 2 + inset
        bottom = cy + size / 2 - inset
        mid_x = cx
        mid_y = cy
        w = right - left
        h = bottom - top

        pen = QPen(stroke_color, stroke_w)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        # ── "S" — built from two opposing arcs ──
        s_arc_h = h * 0.48  # height of each S half-arc
        s_arc_w = w * 0.52

        s_top_rect = QRectF(mid_x - s_arc_w * 0.42, top,
                            s_arc_w, s_arc_h)
        s_path = QPainterPath()
        s_path.arcMoveTo(s_top_rect, 90)
        s_path.arcTo(s_top_rect, 90, 180)

        s_bot_rect = QRectF(mid_x - s_arc_w * 0.58, bottom - s_arc_h,
                            s_arc_w, s_arc_h)
        s_path.arcTo(s_bot_rect, 270, 180)

        p.drawPath(s_path)

        # ── "C" — open arc wrapping the left side ──
        c_inset = size * 0.015
        c_rect = QRectF(left - c_inset, top + h * 0.05,
                        w * 0.88, h * 0.90)
        c_path = QPainterPath()
        c_path.arcMoveTo(c_rect, 55)
        c_path.arcTo(c_rect, 55, 250)

        p.drawPath(c_path)

    def paintEvent(self, event):
        p = QPainter(self)
        try:
            cx = self.width() / 2
            cy = self.height() / 2
            size = min(self.width(), self.height())

            breath = 0.5 + 0.5 * math.sin(self._phase)
            border_alpha = int(20 + 20 * breath)

            accent_color = QColor(theme_manager.palette.accent)
            self.draw_monogram(p, cx, cy, size, accent_color, border_alpha)
        finally:
            p.end()


class WelcomeView(QWidget):
    """Opening screen with animated logo and tagline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._logo_cache: dict[str, QPixmap] = {}

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(40, 20, 40, 40)

        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.setSpacing(12)

        # ── Welcome title graphic ──
        self.logo_widget = QLabel()
        self.logo_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_logo()
        c_layout.addWidget(self.logo_widget, 0, Qt.AlignmentFlag.AlignCenter)

        c_layout.addSpacing(8)

        tagline_1 = QLabel("Sort It Out")
        tagline_1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        style(tagline_1, lambda p: f"""
            font-size: 16px;
            font-weight: 700;
            color: {p.text_strong};
            letter-spacing: 2px;
        """)

        tagline_2 = QLabel("Adaptive Network Congestion & ISP Diagnostic Engine")
        tagline_2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        style(tagline_2, lambda p: f"""
            font-size: 13px;
            font-weight: 500;
            color: {p.text_muted};
            letter-spacing: 0.5px;
        """)

        c_layout.addWidget(tagline_1)
        c_layout.addWidget(tagline_2)
        c_layout.addSpacing(28)

        hint = QLabel("Select a module from the sidebar to begin")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        style(hint, lambda p: f"""
            font-size: 11px;
            font-weight: 600;
            color: {p.text_faint};
            letter-spacing: 1px;
            background-color: {p.welcome_card_bg};
            border: 1px solid {p.welcome_card_border};
            border-radius: 20px;
            padding: 10px 28px;
        """)
        c_layout.addWidget(hint, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(container)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._anim = QPropertyAnimation(self._opacity, b"opacity")
        self._anim.setDuration(600)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

        theme_manager.changed.connect(lambda _: self._update_logo())

    def _update_logo(self):
        theme_name = theme_manager.name
        if theme_name not in self._logo_cache:
            raw_img = _get_raw_image()
            if theme_name == "dark":
                pixmap = QPixmap.fromImage(raw_img)
            else:
                derived = derive_light_logo(raw_img, theme_manager.palette.accent)
                pixmap = QPixmap.fromImage(derived)
            self._logo_cache[theme_name] = pixmap.scaled(
                480, 255,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.logo_widget.setPixmap(self._logo_cache[theme_name])