import math
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QPen, QRadialGradient, QBrush, QFont, QPainterPath


class AnimatedLogoWidget(QWidget):
    """Hexagonal mesh network logo with data-flow pulses and integrated 'SARICHESKO' text."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(320, 320)
        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def _tick(self):
        self._phase = (self._phase + 0.018) % (2 * math.pi)
        self.update()

    def _hex_points(self, cx, cy, r):
        pts = []
        for i in range(6):
            angle = math.radians(60 * i - 30)
            pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
        return pts

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx, cy = self.width() / 2, self.height() / 2

        # ── Outer hex border (faint) ──
        outer_pts = self._hex_points(cx, cy, 140)
        path_outer = QPainterPath()
        path_outer.moveTo(*outer_pts[0])
        for pt in outer_pts[1:]:
            path_outer.lineTo(*pt)
        path_outer.closeSubpath()
        p.setPen(QPen(QColor(0, 240, 255, 20), 1.0))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path_outer)

        # ── Middle hex ring ──
        mid_pts = self._hex_points(cx, cy, 100)
        path_mid = QPainterPath()
        path_mid.moveTo(*mid_pts[0])
        for pt in mid_pts[1:]:
            path_mid.lineTo(*pt)
        path_mid.closeSubpath()
        p.setPen(QPen(QColor(0, 240, 255, 50), 1.2))
        p.drawPath(path_mid)

        # ── Inner hex ring (brighter) ──
        inner_pts = self._hex_points(cx, cy, 58)
        path_inner = QPainterPath()
        path_inner.moveTo(*inner_pts[0])
        for pt in inner_pts[1:]:
            path_inner.lineTo(*pt)
        path_inner.closeSubpath()
        p.setPen(QPen(QColor(0, 240, 255, 90), 1.5))
        p.drawPath(path_inner)

        # ── Cross-connections: inner hex vertices to mid hex vertices ──
        for i in range(6):
            alpha = int(30 + 25 * math.sin(self._phase * 2 + i))
            p.setPen(QPen(QColor(0, 240, 255, alpha), 0.6))
            p.drawLine(int(inner_pts[i][0]), int(inner_pts[i][1]),
                       int(mid_pts[i][0]), int(mid_pts[i][1]))
            p.drawLine(int(mid_pts[i][0]), int(mid_pts[i][1]),
                       int(outer_pts[i][0]), int(outer_pts[i][1]))

        # ── Data pulse particles traveling along edges ──
        for i in range(6):
            t = (self._phase * 1.5 + i * 1.047) % (2 * math.pi)
            progress = (t / (2 * math.pi))

            # Pulse on mid-hex edges
            x0, y0 = mid_pts[i]
            x1, y1 = mid_pts[(i + 1) % 6]
            px = x0 + (x1 - x0) * progress
            py = y0 + (y1 - y0) * progress

            pulse_grad = QRadialGradient(px, py, 10)
            pulse_grad.setColorAt(0.0, QColor(0, 240, 255, 200))
            pulse_grad.setColorAt(1.0, QColor(0, 240, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(pulse_grad))
            p.drawEllipse(px - 10, py - 10, 20, 20)

            p.setBrush(QBrush(QColor(0, 240, 255, 255)))
            p.drawEllipse(px - 3, py - 3, 6, 6)

        # ── Vertex nodes on mid hex (junction dots) ──
        for i, (mx, my) in enumerate(mid_pts):
            glow = int(60 + 40 * math.sin(self._phase * 3 + i * 0.8))
            node_grad = QRadialGradient(mx, my, 9)
            node_grad.setColorAt(0.0, QColor(0, 240, 255, 180))
            node_grad.setColorAt(1.0, QColor(0, 240, 255, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(node_grad))
            p.drawEllipse(mx - 9, my - 9, 18, 18)

            p.setBrush(QBrush(QColor(0, 240, 255)))
            p.drawEllipse(mx - 4, my - 4, 8, 8)

        # ── Core glow ──
        pulse = 1.0 + 0.05 * math.sin(self._phase * 2.5)
        cr = 30 * pulse

        grad = QRadialGradient(cx, cy, cr * 1.8)
        grad.setColorAt(0.0, QColor(0, 240, 255, 200))
        grad.setColorAt(0.4, QColor(0, 200, 220, 80))
        grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawEllipse(cx - cr * 1.8, cy - cr * 1.8, cr * 3.6, cr * 3.6)

        # ── Center core node ──
        p.setBrush(QBrush(QColor(0, 240, 255)))
        p.drawEllipse(cx - 10, cy - 10, 20, 20)

        # ── "SARICHESKO" text arc across the center ──
        text = "SARICHESKO"
        font = QFont("Segoe UI", 11, QFont.Weight.Bold)
        p.setFont(font)

        arc_radius = 78
        total_arc = 100  # degrees
        start_angle = 270 - total_arc / 2

        for i, ch in enumerate(text):
            angle_deg = start_angle + (i / (len(text) - 1)) * total_arc
            angle_rad = math.radians(angle_deg)
            tx = cx + arc_radius * math.cos(angle_rad)
            ty = cy + arc_radius * math.sin(angle_rad)

            # Shimmer effect
            shimmer = math.sin(self._phase * 3 + i * 0.5)
            alpha = int(180 + 75 * shimmer)
            p.setPen(QColor(0, 240, 255, alpha))

            p.save()
            p.translate(tx, ty)
            p.rotate(angle_deg + 90)
            p.drawText(-5, 4, ch)
            p.restore()


class WelcomeView(QWidget):
    """Opening screen with animated logo and tagline."""
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(40, 20, 40, 40)

        container = QWidget()
        c_layout = QVBoxLayout(container)
        c_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        c_layout.setSpacing(12)

        self.logo_widget = AnimatedLogoWidget()
        c_layout.addWidget(self.logo_widget, 0, Qt.AlignmentFlag.AlignCenter)

        c_layout.addSpacing(8)

        title = QLabel("SariChesko")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""
            font-size: 48px;
            font-weight: 800;
            color: #00f0ff;
            letter-spacing: 3px;
        """)
        c_layout.addWidget(title)

        tagline_1 = QLabel("Sort It Out")
        tagline_1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline_1.setStyleSheet("""
            font-size: 16px;
            font-weight: 700;
            color: #ffffff;
            letter-spacing: 2px;
        """)

        tagline_2 = QLabel("Adaptive Network Congestion & ISP Diagnostic Engine")
        tagline_2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline_2.setStyleSheet("""
            font-size: 13px;
            font-weight: 500;
            color: #64748b;
            letter-spacing: 0.5px;
        """)

        c_layout.addWidget(tagline_1)
        c_layout.addWidget(tagline_2)
        c_layout.addSpacing(28)

        hint = QLabel("Select a module from the sidebar to begin")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("""
            font-size: 11px;
            font-weight: 600;
            color: #475569;
            letter-spacing: 1px;
            background-color: #060810;
            border: 1px solid #141824;
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