import sys
import ctypes

from PySide6.QtWidgets import QApplication

from .storage.db import get_connection, init_db
from .ui.main_window import MainWindow
from .ui.theme import load_saved_theme, theme_manager
from .ui.icon import create_app_icon


def _set_dark_title_bar(window, dark: bool = True):
    """Set title bar theme on Windows 10/11 (dark=True for dark, dark=False for light)."""
    if sys.platform != "win32":
        return
    try:
        hwnd = int(window.winId())
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1 if dark else 0)
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

    # Load saved theme before MainWindow creation so there is no theme flash
    load_saved_theme()

    icon = create_app_icon()
    app.setWindowIcon(icon)

    conn = get_connection()
    init_db(conn)
    conn.close()

    window = MainWindow()
    window.setWindowIcon(icon)
    _set_dark_title_bar(window, dark=(theme_manager.name == "dark"))
    theme_manager.changed.connect(lambda name: _set_dark_title_bar(window, dark=(name == "dark")))
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()