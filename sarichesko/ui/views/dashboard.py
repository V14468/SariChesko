from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve


class DashboardView(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(24)

        # Hero Header Box
        hero_box = QWidget()
        hero_layout = QVBoxLayout(hero_box)
        hero_layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("SariChesko")
        title.setObjectName("hero_title")

        tagline = QLabel("Telugu: \"Sort it out\"  •  Adaptive Network Congestion & ISP Diagnostic Engine")
        tagline.setObjectName("hero_subtitle")

        hero_layout.addWidget(title)
        hero_layout.addWidget(tagline)
        layout.addWidget(hero_box)

        # Quick Status Cards Row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(16)

        cards_data = [
            ("Network Status", "Monitoring Active", "#00e5a3", "Real-time interface telemetry listening"),
            ("ISP Diagnostics", "Gateway Reachable", "#00f0ff", "Level 1-5 multi-target probe ready"),
            ("Congestion Engine", "Zero Active Dropping", "#94a3b8", "Leaky / Token Bucket & RED / CoDel Idle"),
        ]

        for card_title, status_val, color, desc in cards_data:
            card = QFrame()
            card.setObjectName("card")
            c_layout = QVBoxLayout(card)
            c_layout.setSpacing(8)

            lbl_t = QLabel(card_title)
            lbl_t.setStyleSheet("font-size: 12px; font-weight: 600; color: #64748b;")

            lbl_v = QLabel(status_val)
            lbl_v.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {color};")

            lbl_d = QLabel(desc)
            lbl_d.setStyleSheet("font-size: 12px; color: #94a3b8;")
            lbl_d.setWordWrap(True)

            c_layout.addWidget(lbl_t)
            c_layout.addWidget(lbl_v)
            c_layout.addWidget(lbl_d)
            cards_row.addWidget(card)

        layout.addLayout(cards_row)

        # CTA Section
        cta_frame = QFrame()
        cta_frame.setObjectName("card")
        cta_layout = QHBoxLayout(cta_frame)
        cta_layout.setContentsMargins(24, 24, 24, 24)

        info_v = QVBoxLayout()
        t_cta = QLabel("Run Network Diagnostic")
        t_cta.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        d_cta = QLabel("Measure latency variance, packet loss, and classify local vs. ISP bottlenecks.")
        d_cta.setStyleSheet("font-size: 13px; color: #94a3b8;")
        info_v.addWidget(t_cta)
        info_v.addWidget(d_cta)

        btn_run = QPushButton("Start Diagnostic")
        btn_run.setObjectName("primary_btn")
        btn_run.setCursor(Qt.CursorShape.PointingHandCursor)

        cta_layout.addLayout(info_v)
        cta_layout.addStretch()
        cta_layout.addWidget(btn_run)

        layout.addWidget(cta_frame)
        layout.addStretch()

        # Fade-in animation on opening view
        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._anim = QPropertyAnimation(self._opacity, b"opacity")
        self._anim.setDuration(450)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()