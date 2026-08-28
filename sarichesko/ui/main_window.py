from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QFrame, QPushButton, QStackedWidget, QLabel,
)
from PySide6.QtCore import Qt

from .views.welcome import WelcomeView
from .views.dashboard import DashboardView
from .views.diagnose import DiagnoseView
from .views.live_network import LiveNetworkView
from .views.simulation_lab import SimulationLabView
from .views.compare_algorithms import CompareAlgorithmsView
from .views.history import HistoryView
from .views.reports import ReportsView
from .views.settings import SettingsView


NAV_ITEMS = [
    ("Dashboard", DashboardView),
    ("Diagnose", DiagnoseView),
    ("Live Network", LiveNetworkView),
    ("Simulation Lab", SimulationLabView),
    ("Compare", CompareAlgorithmsView),
    ("History", HistoryView),
    ("Reports", ReportsView),
    ("Settings", SettingsView),
]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SariChesko — Adaptive Congestion Management")
        self.setMinimumSize(1150, 720)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # AMOLED Black Sidebar
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 24, 12, 20)
        sidebar_layout.setSpacing(6)

        # Sidebar Logo Header (Clicking returns to Welcome Screen)
        self.logo_btn = QPushButton("SariChesko")
        self.logo_btn.setStyleSheet("""
            QPushButton {
                font-size: 22px;
                font-weight: 800;
                color: #00f0ff;
                letter-spacing: 1px;
                background: transparent;
                border: none;
                outline: none;
                text-align: left;
                padding: 4px 0px;
            }
            QPushButton:focus {
                outline: none;
            }
            QPushButton:hover {
                color: #33f3ff;
            }
        """)
        self.logo_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        tagline = QLabel("SORT IT OUT  •  NETENGINE")
        tagline.setObjectName("sidebar_tagline")

        sidebar_layout.addWidget(self.logo_btn)
        sidebar_layout.addWidget(tagline)
        sidebar_layout.addSpacing(16)

        # Main Nav Stack
        self._stack = QStackedWidget()
        self._stack.setObjectName("content")
        self._nav_buttons: list[QPushButton] = []

        # Index 0: Welcome Screen (Opens First!)
        welcome_view = WelcomeView()
        self._welcome_idx = self._stack.addWidget(welcome_view)
        self.logo_btn.clicked.connect(self._show_welcome)

        # Index 1..N: Sidebar views
        for name, view_class in NAV_ITEMS:
            btn = QPushButton(name)
            btn.setObjectName("nav_button")
            btn.setCheckable(True)
            btn.setFixedHeight(44)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

            idx = self._stack.addWidget(view_class())
            btn.clicked.connect(lambda checked, i=idx, b=btn: self._navigate(i, b))
            sidebar_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        sidebar_layout.addStretch()

        layout.addWidget(sidebar)
        layout.addWidget(self._stack)

        # Open initially on the Welcome Screen (index 0)
        self._show_welcome()

    def _show_welcome(self) -> None:
        for b in self._nav_buttons:
            b.setChecked(False)
        self._stack.setCurrentIndex(self._welcome_idx)

    def _navigate(self, index: int, button: QPushButton) -> None:
        for b in self._nav_buttons:
            b.setChecked(False)
        button.setChecked(True)
        self._stack.setCurrentIndex(index)