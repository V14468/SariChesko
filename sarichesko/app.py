import sys
import time

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

from .storage.db import get_connection, init_db
from .ui.main_window import MainWindow
from .ui.splash import SplashScreen
from .ui.theme import OLED_BLACK_THEME


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SariChesko")
    app.setStyleSheet(OLED_BLACK_THEME)

    # Show Splash Screen first
    splash = SplashScreen()
    splash.show()
    splash.start_animation()
    app.processEvents()

    # Step 1: Database init
    splash.update_status("Initializing SQLite database...", 30)
    app.processEvents()
    time.sleep(0.3)
    conn = get_connection()
    init_db(conn)
    conn.close()

    # Step 2: Core Platform Layer check
    splash.update_status("Detecting Platform Abstraction Layer...", 65)
    app.processEvents()
    time.sleep(0.3)

    # Step 3: UI Main Window construction
    splash.update_status("Loading UI components...", 90)
    app.processEvents()
    time.sleep(0.3)

    window = MainWindow()

    splash.update_status("Ready!", 100)
    app.processEvents()
    time.sleep(0.2)

    # Transition from Splash to Main Window
    splash.close()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()