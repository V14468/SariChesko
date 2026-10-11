"""Tests for package version and single-source-of-truth verification."""
import re
import pytest
from sarichesko import __version__


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    from PySide6.QtWidgets import QApplication
    yield QApplication.instance() or QApplication([])


def test_version_format():
    """Verify that __version__ follows semantic versioning (X.Y.Z)."""
    assert isinstance(__version__, str)
    assert re.match(r"^\d+\.\d+\.\d+$", __version__) is not None
    assert __version__ == "1.0.0"


def test_settings_about_displays_version():
    """Verify that SettingsView includes __version__ in its about card."""
    from sarichesko.ui.views.settings import SettingsView
    from PySide6.QtWidgets import QLabel

    view = SettingsView()
    labels = view.findChildren(QLabel)
    expected_text = f"SariChesko v{__version__}"
    found = any(expected_text in label.text() for label in labels)
    assert found, f"Could not find label with '{expected_text}' in SettingsView"
