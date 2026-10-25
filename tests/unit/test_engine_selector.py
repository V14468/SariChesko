"""Unit tests for sarichesko.ui.widgets.engine_selector."""
import pytest
from PySide6.QtWidgets import QApplication

from sarichesko.ui.widgets.engine_selector import EngineSelector
from sarichesko.simulation.ns3_bridge import Ns3Status
from sarichesko.simulation.python_sim import PythonSimulationEngine
from sarichesko.simulation.ns3_bridge import Ns3SimulationEngine


@pytest.fixture(autouse=True)
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestEngineSelector:
    """Test EngineSelector widget behavior and engine dispatch."""

    def test_default_engine_is_python(self):
        sel = EngineSelector()
        engine = sel.build_engine()
        assert isinstance(engine, PythonSimulationEngine)
        assert sel.engine_name == "Built-in Python"

    def test_ns3_disabled_when_not_ready(self, monkeypatch):
        fake_status = Ns3Status(
            state="unavailable",
            message="ns-3 is not available on Windows.",
        )
        monkeypatch.setattr(
            "sarichesko.ui.widgets.engine_selector.ns3_status",
            lambda: fake_status,
        )

        sel = EngineSelector()
        model = sel._combo.model()
        item = model.item(1)
        assert item is not None
        assert not item.isEnabled()
        assert "Windows" in sel._status_label.text()

        # Even if somehow forced to index 1, build_engine still falls back to Python
        sel._combo.setCurrentIndex(1)
        assert isinstance(sel.build_engine(), PythonSimulationEngine)

    def test_ns3_enabled_when_ready(self, monkeypatch):
        fake_status = Ns3Status(
            state="ready",
            message="ns-3 ready at /fake/ns3 with sarichesko-sim scenario.",
            launcher="/fake/ns3/ns3",
        )
        monkeypatch.setattr(
            "sarichesko.ui.widgets.engine_selector.ns3_status",
            lambda: fake_status,
        )

        sel = EngineSelector()
        model = sel._combo.model()
        item = model.item(1)
        assert item is not None
        assert item.isEnabled()
        assert "ready" in sel._status_label.text().lower()

        # Select ns-3
        sel._combo.setCurrentIndex(1)
        assert sel.engine_name == "ns-3"
        engine = sel.build_engine()
        assert isinstance(engine, Ns3SimulationEngine)
