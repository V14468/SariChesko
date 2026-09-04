import sys
import math
import ctypes

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QPainter, QColor, QPen, QIcon, QPainterPath
from PySide6.QtCore import Qt

from .storage.db import get_connection, init_db
from .ui.main_window import MainWindow
from .ui.theme import OLED_BLACK_THEME


def _create_app_icon() -> QIcon:
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))

    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    cx, cy = size / 2, size / 2
    r = 28

    pts = []
    for i in range(6):
        angle = math.radians(60 * i - 30)
        pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))

    path = QPainterPath()
    path.moveTo(*pts[0])
    for pt in pts[1:]:
        path.lineTo(*pt)
    path.closeSubpath()

    p.setPen(QPen(QColor(0, 240, 255), 2.0))
    p.setBrush(QColor(0, 240, 255, 40))
    p.drawPath(path)

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 240, 255))
    p.drawEllipse(cx - 5, cy - 5, 10, 10)

    inner_r = 12
    p.setPen(QPen(QColor(0, 240, 255, 120), 1.0))
    for i in range(6):
        angle = math.radians(60 * i - 30)
        ix = cx + inner_r * math.cos(angle)
        iy = cy + inner_r * math.sin(angle)
        p.drawLine(int(cx), int(cy), int(ix), int(iy))
        p.setBrush(QColor(0, 240, 255))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(ix - 2, iy - 2, 4, 4)
        p.setPen(QPen(QColor(0, 240, 255, 120), 1.0))

    p.end()
    return QIcon(pixmap)


def _set_dark_title_bar(window):
    """Force dark title bar on Windows 10/11."""
    try:
        hwnd = int(window.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value), ctypes.sizeof(value)
        )
    except Exception:
        pass


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SariChesko")
    app.setStyleSheet(OLED_BLACK_THEME)

    icon = _create_app_icon()
    app.setWindowIcon(icon)

    conn = get_connection()
    init_db(conn)
    conn.close()

    window = MainWindow()
    window.setWindowIcon(icon)
    _set_dark_title_bar(window)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()