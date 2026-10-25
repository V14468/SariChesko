"""Simulation engine selector widget.

A combo box allowing the user to choose between the built-in Python
discrete-event simulation engine and the ns-3 subprocess bridge.
The ns-3 option is present but DISABLED unless ns3_status().state == "ready".

A one-line status label shows ns3_status().message so the user always
knows why ns-3 is or isn't available.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
)
from PySide6.QtGui import QStandardItemModel

from ...simulation.ns3_bridge import ns3_status, Ns3Status, Ns3SimulationEngine
from ...simulation.python_sim import PythonSimulationEngine
from ...simulation.engine_base import SimulationEngineBase
from ..theme import style, Palette


_IDX_PYTHON = 0
_IDX_NS3 = 1


def _status_color(state: str, p: Palette) -> str:
    if state == "ready":
        return p.success
    elif state == "scenario_missing":
        return p.warning
    return p.text_muted


class EngineSelector(QWidget):
    """Compact widget that lets the user pick a simulation engine.

    Usage in a config card::

        self._engine_sel = EngineSelector()
        config_layout.addWidget(self._engine_sel)

        # Later, when running:
        engine = self._engine_sel.build_engine()
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._status: Ns3Status = ns3_status()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # Engine label
        engine_col = QVBoxLayout()
        engine_col.setSpacing(4)
        lbl = QLabel("Simulation Engine")
        style(lbl, lambda p: f"font-size: 12px; font-weight: 600; color: {p.text_secondary};")
        engine_col.addWidget(lbl)

        self._combo = QComboBox()
        self._combo.setFixedHeight(36)
        self._combo.setMinimumWidth(220)
        self._combo.addItem("Built-in Python (default)")
        self._combo.addItem("ns-3")

        # Disable the ns-3 item if not ready
        if self._status.state != "ready":
            model = self._combo.model()
            if isinstance(model, QStandardItemModel):
                item = model.item(_IDX_NS3)
                if item is not None:
                    item.setEnabled(False)

        engine_col.addWidget(self._combo)
        layout.addLayout(engine_col)

        # Status label
        status_col = QVBoxLayout()
        status_col.setSpacing(4)
        spacer_lbl = QLabel("")  # align with combo label
        spacer_lbl.setStyleSheet("font-size: 12px;")
        status_col.addWidget(spacer_lbl)

        self._status_label = QLabel(self._status.message)
        self._status_label.setWordWrap(True)
        self._status_label.setMinimumHeight(36)

        style(
            self._status_label,
            lambda p: f"font-size: 11px; color: {_status_color(self._status.state, p)};"
        )
        status_col.addWidget(self._status_label)
        layout.addLayout(status_col)

        layout.addStretch()

    def build_engine(self) -> SimulationEngineBase:
        """Return the engine selected by the user.

        If ns-3 is selected and ready, returns Ns3SimulationEngine (which
        itself falls back to Python if the subprocess fails).
        Otherwise returns PythonSimulationEngine.
        """
        if self._combo.currentIndex() == _IDX_NS3 and self._status.state == "ready":
            return Ns3SimulationEngine()
        return PythonSimulationEngine()

    @property
    def engine_name(self) -> str:
        """Human-readable name of the currently selected engine."""
        if self._combo.currentIndex() == _IDX_NS3:
            return "ns-3"
        return "Built-in Python"
