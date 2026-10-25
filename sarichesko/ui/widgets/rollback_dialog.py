from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt

from ..theme import Palette, style


def verdict_display(p: Palette) -> dict:
    return {
        "improved": ("Improved", p.success),
        "worse": ("Got Worse", p.danger),
        "no_change": ("No Significant Change", p.text_secondary),
    }


def _metric_row(label: str, before, after, unit: str, lower_is_better: bool = True) -> QFrame:
    row = QFrame()
    hl = QHBoxLayout(row)
    hl.setContentsMargins(0, 4, 0, 4)
    hl.setSpacing(10)

    lbl = QLabel(label)
    style(lbl, lambda p: f"font-size: 12px; color: {p.text_secondary};")
    lbl.setFixedWidth(110)
    hl.addWidget(lbl)

    if before is None or after is None:
        val_lbl = QLabel("\u2014")
        style(val_lbl, lambda p: f"font-size: 12px; color: {p.text_muted};")
        hl.addWidget(val_lbl)
        hl.addStretch()
        return row

    def _color(p: Palette) -> str:
        improved = (after < before) if lower_is_better else (after > before)
        return p.success if improved else (p.danger if after != before else p.text_secondary)

    val_lbl = QLabel(f"{before:.2f} {unit}  \u2192  {after:.2f} {unit}")
    style(val_lbl, lambda p: f"font-size: 13px; font-weight: 700; color: {_color(p)};")
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
        style(self, lambda p: f"""
            QDialog {{ background-color: {p.surface_raised}; }}
            QLabel {{ color: {p.text}; }}
        """)
        self.rollback_requested = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel(f"{algo_name} applied to your network")
        style(title, lambda p: f"font-size: 16px; font-weight: 800; color: {p.text_strong};")
        title.setWordWrap(True)
        layout.addWidget(title)

        if apply_message:
            msg = QLabel(apply_message)
            style(msg, lambda p: f"font-size: 11px; color: {p.text_muted};")
            msg.setWordWrap(True)
            layout.addWidget(msg)

        card = QFrame()
        card.setObjectName("card")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(18, 16, 18, 16)
        cl.setSpacing(6)

        verdict_title = QLabel("VERIFICATION")
        style(verdict_title, lambda p: f"font-size: 10px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")
        cl.addWidget(verdict_title)

        v_lbl = QLabel()
        if verdict is None:
            v_lbl.setText("Could not verify (see message above)")
            style(v_lbl, lambda p: f"font-size: 16px; font-weight: 800; color: {p.text_secondary};")
        else:
            style(v_lbl, lambda p: f"font-size: 16px; font-weight: 800; color: {verdict_display(p).get(verdict, ('Unknown', p.text_secondary))[1]};")
            # Set initial text
            from ..theme import theme_manager
            v_text, _ = verdict_display(theme_manager.palette).get(verdict, ("Unknown", theme_manager.palette.text_secondary))
            v_lbl.setText(v_text)
        cl.addWidget(v_lbl)

        if score_after is not None:
            score_lbl = QLabel(f"Congestion score: {score_before:.0f} \u2192 {score_after:.0f}")
            style(score_lbl, lambda p: f"font-size: 12px; color: {p.text_secondary};")
            cl.addWidget(score_lbl)

        cl.addWidget(_metric_row("Latency", latency_before, latency_after, "ms", lower_is_better=True))
        cl.addWidget(_metric_row("Packet loss", loss_before, loss_after, "%", lower_is_better=True))

        layout.addWidget(card)

        note = QLabel(
            "You can keep this change or roll it back to your previous settings right now. "
            "SariChesko will not change anything further without asking again."
        )
        style(note, lambda p: f"font-size: 11px; color: {p.text_muted};")
        note.setWordWrap(True)
        layout.addWidget(note)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._btn_rollback = QPushButton("Roll Back")
        self._btn_rollback.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_rollback.setFixedHeight(36)
        style(self._btn_rollback, lambda p: f"""
            QPushButton {{ background-color: {p.danger_bg}; color: {p.danger}; border: 1px solid {p.danger_border}; border-radius: 8px; padding: 6px 16px; font-weight: 700; }}
            QPushButton:hover {{ background-color: {p.danger_bg_hover}; }}
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
            style(self._btn_keep, lambda p: (
                f"QPushButton {{ background-color: {p.dialog_btn}; color: {p.text_secondary}; border: 1px solid {p.border_strong}; "
                "border-radius: 8px; padding: 6px 16px; font-weight: 700; }"
            ))
            style(self._btn_rollback, lambda p: f"""
                QPushButton {{ background-color: {p.danger}; color: {p.surface_raised}; border: none; border-radius: 8px; padding: 6px 16px; font-weight: 800; }}
                QPushButton:hover {{ background-color: {p.danger_hover}; }}
            """)

    def _on_rollback(self):
        self.rollback_requested = True
        self.accept()