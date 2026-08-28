import time
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QGraphicsOpacityEffect
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer


class SplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(520, 320)

        # Container with dark border & blur feel
        container = QWidget(self)
        container.setGeometry(0, 0, 520, 320)
        container.setStyleSheet("""
            QWidget {
                background-color: #050509;
                border: 1px solid #1e2030;
                border-radius: 16px;
            }
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(40, 40, 40, 30)

        # Logo & App Title
        title = QLabel("SariChesko")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""
            font-size: 38px;
            font-weight: 800;
            color: #00f0ff;
            letter-spacing: 2px;
            border: none;
        """)
        layout.addWidget(title)

        # Telugu meaning + Tagline
        tagline = QLabel("Telugu: \"Sort it out\"\nAdaptive Congestion Management & ISP Diagnostics")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet("""
            font-size: 13px;
            font-weight: 500;
            color: #94a3b8;
            line-height: 1.4;
            border: none;
        """)
        layout.addWidget(tagline)

        layout.addStretch()

        # Status text during splash load
        self.status_label = QLabel("Initializing Platform Abstraction Layer...")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("""
            font-size: 11px;
            color: #64748b;
            border: none;
        """)
        layout.addWidget(self.status_label)

        # Minimal progress bar
        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("""
            QProgressBar {
                background-color: #121420;
                border: none;
                border-radius: 2px;
            }
            QProgressBar::chunk {
                background-color: #00f0ff;
                border-radius: 2px;
            }
        """)
        layout.addWidget(self.progress)

        # Opacity animation for smooth fade-in
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(600)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)

    def start_animation(self):
        self.fade_anim.start()

    def update_status(self, text: str, value: int):
        self.status_label.setText(text)
        self.progress.setValue(value)