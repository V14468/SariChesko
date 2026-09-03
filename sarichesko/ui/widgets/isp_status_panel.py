from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
from PySide6.QtCore import Qt

from ...core.isp_probe import ISPDiagnosticResult, ISPVerdict


VERDICT_DISPLAY = {
    ISPVerdict.HEALTHY: ("Healthy", "#00e5a3"),
    ISPVerdict.LOCAL_CONGESTION: ("Local Congestion", "#f59e0b"),
    ISPVerdict.LAST_MILE: ("Last Mile Issue", "#ef4444"),
    ISPVerdict.ISP_DEGRADATION: ("ISP Degradation", "#f59e0b"),
    ISPVerdict.ISP_OUTAGE: ("ISP Outage", "#ef4444"),
    ISPVerdict.DNS_ISSUE: ("DNS Issue", "#ef4444"),
}


class ISPStatusPanel(QWidget):
    """Displays ISP probe results as a vertical status card."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)

        self._title = QLabel("ISP DIAGNOSTICS")
        self._title.setStyleSheet("font-size: 11px; font-weight: 700; color: #64748b; letter-spacing: 0.8px;")
        self._layout.addWidget(self._title)

        self._verdict_label = QLabel("Not tested")
        self._verdict_label.setStyleSheet("font-size: 20px; font-weight: 700; color: #475569;")
        self._layout.addWidget(self._verdict_label)

        self._details_label = QLabel("")
        self._details_label.setStyleSheet("font-size: 12px; color: #94a3b8;")
        self._details_label.setWordWrap(True)
        self._layout.addWidget(self._details_label)

        self._probes_container = QVBoxLayout()
        self._probes_container.setSpacing(6)
        self._layout.addLayout(self._probes_container)
        self._layout.addStretch()

    def update_result(self, result: ISPDiagnosticResult):
        display_text, color = VERDICT_DISPLAY.get(result.verdict, ("Unknown", "#64748b"))
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

            status_color = "#00e5a3" if probe.ping.success else "#ef4444"
            dot = QLabel("●")
            dot.setStyleSheet(f"font-size: 10px; color: {status_color};")
            dot.setFixedWidth(14)

            name = QLabel(probe.label)
            name.setStyleSheet("font-size: 12px; font-weight: 600; color: #e2e8f0;")

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