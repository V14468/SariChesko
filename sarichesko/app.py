import sys
import ctypes

from PySide6.QtWidgets import QApplication

from .storage.db import get_connection, init_db
from .ui.main_window import MainWindow
from .ui.theme import OLED_BLACK_THEME
from .ui.icon import create_app_icon


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
    if sys.platform == "win32":
        # Give the process its own taskbar identity so Windows shows the
        # SariChesko icon (not python.exe's) and groups its windows correctly.
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SariChesko.NetEngine")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("SariChesko")
    app.setStyleSheet(OLED_BLACK_THEME)

    icon = create_app_icon()
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