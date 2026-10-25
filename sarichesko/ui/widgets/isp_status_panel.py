from typing import Optional
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

from ...core.isp_probe import ISPDiagnosticResult, ISPVerdict
from ..theme import theme_manager, Palette, style


def verdict_display(p: Palette) -> dict:
    return {
        ISPVerdict.HEALTHY: ("Healthy", p.success),
        ISPVerdict.LOCAL_CONGESTION: ("Local Congestion", p.warning),
        ISPVerdict.LAST_MILE: ("Last Mile Issue", p.danger),
        ISPVerdict.ISP_DEGRADATION: ("ISP Degradation", p.warning),
        ISPVerdict.ISP_OUTAGE: ("ISP Outage", p.danger),
        ISPVerdict.DNS_ISSUE: ("DNS Issue", p.danger),
    }


class ISPStatusPanel(QWidget):
    """Displays ISP probe results as a vertical status card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._last_result: Optional[ISPDiagnosticResult] = None

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)

        self._title = QLabel("ISP DIAGNOSTICS")
        style(self._title, lambda p: f"font-size: 11px; font-weight: 700; color: {p.text_muted}; letter-spacing: 0.8px;")
        self._layout.addWidget(self._title)

        self._verdict_label = QLabel("Not tested")
        style(self._verdict_label, lambda p: (
            f"font-size: 20px; font-weight: 700; color: {p.text_faint};"
            if self._last_result is None else
            f"font-size: 20px; font-weight: 700; color: {verdict_display(p).get(self._last_result.verdict, ('Unknown', p.text_muted))[1]};"
        ))
        self._layout.addWidget(self._verdict_label)

        self._details_label = QLabel("")
        style(self._details_label, lambda p: f"font-size: 12px; color: {p.text_secondary};")
        self._details_label.setWordWrap(True)
        self._layout.addWidget(self._details_label)

        self._probes_container = QVBoxLayout()
        self._probes_container.setSpacing(6)
        self._layout.addLayout(self._probes_container)
        self._layout.addStretch()

        theme_manager.changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _name: str):
        if self._last_result is not None:
            self.update_result(self._last_result)

    def update_result(self, result: ISPDiagnosticResult):
        self._last_result = result
        p = theme_manager.palette
        display_text, color = verdict_display(p).get(result.verdict, ("Unknown", p.text_muted))
        self._verdict_label.setText(display_text)
        self._verdict_label.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {color};")
        self._details_label.setText(result.details)

        # Clear old probe rows
        while self._probes_container.count():
            item = self._probes_container.takeAt(0)
            if item.layout():
                while item.layout().count():
                    child = item.layout().takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()

        # Add probe rows
        for probe in result.probe_results:
            row = QHBoxLayout()
            row.setSpacing(8)

            status_color = p.success if probe.ping.success else p.danger
            dot = QLabel("●")
            dot.setStyleSheet(f"font-size: 10px; color: {status_color};")
            dot.setFixedWidth(14)

            name = QLabel(probe.label)
            name.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {p.text};")

            if probe.ping.latency_ms is not None:
                val_text = f"{probe.ping.latency_ms:.0f} ms"
            elif probe.ping.success:
                val_text = "OK"
            else:
                val_text = "Failed"
            val = QLabel(val_text)
            val.setStyleSheet(f"font-size: 12px; font-weight: 600; color: {status_color};")
            val.setAlignment(Qt.AlignmentFlag.AlignRight)

            row.addWidget(dot)
            row.addWidget(name)
            row.addStretch()
            row.addWidget(val)
            self._probes_container.addLayout(row)