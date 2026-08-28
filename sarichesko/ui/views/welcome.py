import math
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QPen, QRadialGradient, QBrush, QFont


class AnimatedLogoWidget(QWidget):
    """Custom vector-drawn pulsing network logo with glowing radar/signal waves."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(260, 260)
        self._phase = 0.0

        # 60 FPS animation timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_animation)
        self._timer.start(16)

    def _update_animation(self):
        self._phase = (self._phase + 0.025) % (2 * math.pi)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2

        # Glowing outer pulse rings
        for i in range(4):
            ring_phase = (self._phase + i * 0.9) % (2 * math.pi)
            radius = 45 + (ring_phase / (2 * math.pi)) * 75
            alpha = int(255 * (1.0 - (radius - 45) / 75))
            alpha = max(0, min(255, alpha))

            pen = QPen(QColor(0, 240, 255, alpha), 1.8)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        # Core glowing orb gradient
        pulse_scale = 1.0 + 0.08 * math.sin(self._phase * 2)
        core_radius = 40 * pulse_scale

        grad = QRadialGradient(cx, cy, core_radius * 1.5)
        grad.setColorAt(0.0, QColor(0, 240, 255, 240))
        grad.setColorAt(0.5, QColor(0, 229, 163, 160))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(cx - core_radius * 1.5, cy - core_radius * 1.5, core_radius * 3, core_radius * 3)

        # Center core solid node
        painter.setBrush(QBrush(QColor(0, 240, 255)))
        painter.drawEllipse(cx - 14, cy - 14, 28, 28)

        # Orbiting node dots (network traffic indicator)
        for j in range(4):
            angle = self._phase * 1.3 + (j * math.pi / 2)
            orb_r = 78
            ox = cx + orb_r * math.cos(angle)
            oy = cy + orb_r * math.sin(angle)

            painter.setBrush(QBrush(QColor(0, 240, 255 if j % 2 == 0 else 0, 229, 163)))
            painter.drawEllipse(ox - 6, oy - 6, 12, 12)


class WelcomeView(QWidget):
    """Initial central opening screen with centered animated logo & tagline."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(40, 20, 40, 40)

        # Centered container
        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.setSpacing(16)

        # 1. Animated Logo
        self.logo_widget = AnimatedLogoWidget()
        c_layout.addWidget(self.logo_widget, 0, Qt.AlignmentFlag.AlignCenter)

        c_layout.addSpacing(12)

        # 2. Main Centered Title
        title = QLabel("SariChesko")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""
            font-size: 52px;
            font-weight: 800;
            color: #00f0ff;
            letter-spacing: 3px;
        """)
        c_layout.addWidget(title)

        # 3. Clean Taglines (No "Telugu:")
        tagline_1 = QLabel("SariChesko  •  Sort It Out")
        tagline_1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline_1.setStyleSheet("""
            font-size: 17px;
            font-weight: 700;
            color: #ffffff;
            letter-spacing: 1.5px;
        """)

        tagline_2 = QLabel("Adaptive Network Congestion & ISP Diagnostic Engine")
        tagline_2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline_2.setStyleSheet("""
            font-size: 14px;
            font-weight: 500;
            color: #94a3b8;
            letter-spacing: 0.5px;
        """)

        c_layout.addWidget(tagline_1)
        c_layout.addWidget(tagline_2)

        c_layout.addSpacing(28)

        # Prompt hint
        hint = QLabel("Select any module from the sidebar to begin")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("""
            font-size: 12px;
            font-weight: 600;
            color: #64748b;
            letter-spacing: 1px;
            background-color: #080a12;
            border: 1px solid #161a2e;
            border-radius: 20px;
            padding: 10px 28px;
        """)
        c_layout.addWidget(hint, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(container)

        # Smooth fade in
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._anim = QPropertyAnimation(self._opacity, b"opacity")
        self._anim.setDuration(600)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()