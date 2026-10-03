import pytest
from PySide6.QtWidgets import QApplication
from sarichesko.ui.widgets.latency_chart import LatencyChartWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_latency_chart_handles_none_values(qapp):
    """Verify LatencyChartWidget does not crash when receiving None values."""
    widget = LatencyChartWidget()

    # Appending None on empty chart
    widget.add_value(None)
    assert len(widget._data) == 1
    assert widget._data[0] is None
    assert widget._min_val == 0.0

    # Mixed None and valid floats
    widget.add_value(25.0)
    widget.add_value(None)
    widget.add_value(35.0)
    widget.add_value(None)

    assert widget._min_val == 20.0  # min(25, 35) - 5
    assert widget._max_val == 40.0  # max(25, 35) + 5


def test_latency_chart_all_none(qapp):
    """Verify LatencyChartWidget handles multiple consecutive None values safely."""
    widget = LatencyChartWidget()
    for _ in range(10):
        widget.add_value(None)
    assert all(v is None for v in widget._data)
    assert widget._min_val == 0.0
    assert widget._max_val == 1.0
