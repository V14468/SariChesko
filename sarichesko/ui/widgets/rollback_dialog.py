from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt


VERDICT_DISPLAY = {
    "improved": ("Improved", "#00e5a3"),
    "worse": ("Got Worse", "#ef4444"),
    "no_change": ("No Significant Change", "#94a3b8"),
}


def _metric_row(label: str, before, after, unit: str, lower_is_better: bool = True) -> QFrame:
    row = QFrame()
    hl = QHBoxLayout(row)
    hl.setContentsMargins(0, 4, 0, 4)
    hl.setSpacing(10)

    lbl = QLabel(label)
    lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
    lbl.setFixedWidth(110)
    hl.addWidget(lbl)

    if before is None or after is None:
        val_lbl = QLabel("\u2014")
        val_lbl.setStyleSheet("font-size: 12px; color: #64748b;")
        hl.addWidget(val_lbl)
        hl.addStretch()
        return row

    improved = (after < before) if lower_is_better else (after > before)
    color = "#00e5a3" if improved else ("#ef4444" if after != before else "#94a3b8")

    val_lbl = QLabel(f"{before:.2f} {unit}  \u2192  {after:.2f} {unit}")
    val_lbl.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {color};")
    hl.addWidget(val_lbl)
    hl.addStretch()
    return row


class RollbackDialog(QDialog):
    """Shown right after a fix has been applied and re-verified. Presents
    the before/after result and always gives the person a one-click way to
    revert -- applying a fix is never a one-way door."""

    def __init__(self, algo_name: str, score_before: float, score_after,
                 verdict, latency_before=None, latency_after=None,
                 loss_before=None, loss_after=None, apply_message: str = "",
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fix Applied \u2014 Verification Result")
        self.setMinimumWidth(420)
        self.setStyleSheet("""
            QDialog { background-color: #0a0b10; }
            QLabel { color: #e2e8f0; }
        """)
        self.rollback_requested = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel(f"{algo_name} applied to your network")
        title.setStyleSheet("font-size: 16px; font-weight: 800; color: #ffffff;")
        title.setWordWrap(True)
        layout.addWidget(title)

        if apply_message:
            msg = QLabel(apply_message)
            msg.setStyleSheet("font-size: 11px; color: #64748b;")
            msg.setWordWrap(True)
            layout.addWidget(msg)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(6)

        verdict_title = QLabel("VERIFICATION")
        verdict_title.setStyleSheet("font-size: 10px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        cl.addWidget(verdict_title)

        if verdict is None:
            v_lbl = QLabel("Could not verify (see message above)")
            v_lbl.setStyleSheet("font-size: 16px; font-weight: 800; color: #94a3b8;")
        else:
            v_text, v_color = VERDICT_DISPLAY.get(verdict, ("Unknown", "#94a3b8"))
            v_lbl = QLabel(v_text)
            v_lbl.setStyleSheet(f"font-size: 16px; font-weight: 800; color: {v_color};")
        cl.addWidget(v_lbl)

        if score_after is not None:
            score_lbl = QLabel(f"Congestion score: {score_before:.0f} \u2192 {score_after:.0f}")
            score_lbl.setStyleSheet("font-size: 12px; color: #94a3b8;")
            cl.addWidget(score_lbl)

        cl.addWidget(_metric_row("Latency", latency_before, latency_after, "ms", lower_is_better=True))
        cl.addWidget(_metric_row("Packet loss", loss_before, loss_after, "%", lower_is_better=True))

        layout.addWidget(card)

        note = QLabel(
            "You can keep this change or roll it back to your previous settings right now. "
            "SariChesko will not change anything further without asking again."
        )
        note.setStyleSheet("font-size: 11px; color: #64748b;")
        note.setWordWrap(True)
        layout.addWidget(note)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_rollback = QPushButton("Roll Back")
        self._btn_rollback.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_rollback.setFixedHeight(36)
        self._btn_rollback.setStyleSheet("""
            QPushButton { background-color: #1a0f12; color: #ef4444; border: 1px solid #3f1d22; border-radius: 8px; padding: 6px 16px; font-weight: 700; }
            QPushButton:hover { background-color: #2a1216; }
        """)
        self._btn_rollback.clicked.connect(self._on_rollback)
        btn_row.addWidget(self._btn_rollback)

        self._btn_keep = QPushButton("Keep This Fix")
        self._btn_keep.setObjectName("primary_btn")
        self._btn_keep.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_keep.setFixedHeight(36)
        self._btn_keep.clicked.connect(self.accept)
        btn_row.addWidget(self._btn_keep)

        layout.addLayout(btn_row)

        # If verification showed things got worse, make Roll Back the
        # visually emphasized action instead of Keep.
        if verdict == "worse":
            self._btn_keep.setObjectName("")
            self._btn_keep.setStyleSheet(
                "QPushButton { background-color: #12141c; color: #94a3b8; border: 1px solid #1a1d2e; "
                "border-radius: 8px; padding: 6px 16px; font-weight: 700; }"
            )
            self._btn_rollback.setStyleSheet("""
                QPushButton { background-color: #ef4444; color: #0a0b10; border: none; border-radius: 8px; padding: 6px 16px; font-weight: 800; }
                QPushButton:hover { background-color: #f87171; }
            """)

    def _on_rollback(self):
        self.rollback_requested = True
        self.accept()