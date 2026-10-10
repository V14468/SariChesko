"""Elevated-restart behaviour. Nothing here ever shows a real UAC prompt or
starts a real process: the OS call is replaced with a fake."""
import subprocess
import sys
from unittest import mock

import pytest

import sarichesko.platform.windows.controller as wc
from sarichesko.platform.base import ApplyResult
from sarichesko.platform.linux.controller import LinuxTrafficController
from sarichesko.platform.windows.controller import WindowsTrafficController


class TestLaunchCommand:
    def test_packaged_exe_relaunches_itself(self):
        assert wc._app_launch_command(frozen=True, executable=r"C:\App\SariChesko.exe") == [r"C:\App\SariChesko.exe"]

    def test_source_run_relaunches_via_module(self):
        assert wc._app_launch_command(frozen=False, executable="python.exe") == ["python.exe", "-m", "sarichesko.app"]


@pytest.fixture
def as_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    # ctypes.windll doesn't exist off Windows -> is_elevated() safely reports False
    monkeypatch.setattr(WindowsTrafficController, "is_elevated", lambda self: False)


class TestWindowsRelaunch:
    def test_accepted_request_reports_success(self, as_windows, monkeypatch):
        calls = []
        monkeypatch.setattr(wc, "_shell_execute_runas", lambda exe, params, cwd: calls.append((exe, params)) or 42)
        result = WindowsTrafficController().relaunch_elevated()
        assert result.success is True
        assert len(calls) == 1

    @pytest.mark.parametrize("code", [0, 5, 31])
    def test_declined_or_failed_request_is_not_success(self, as_windows, monkeypatch, code):
        monkeypatch.setattr(wc, "_shell_execute_runas", lambda *a: code)
        result = WindowsTrafficController().relaunch_elevated()
        assert result.success is False
        assert "still running" in result.message  # tells the user nothing changed

    def test_os_call_raising_never_propagates(self, as_windows, monkeypatch):
        def boom(*a):
            raise OSError("nope")
        monkeypatch.setattr(wc, "_shell_execute_runas", boom)
        result = WindowsTrafficController().relaunch_elevated()
        assert result.success is False and "nope" in result.message

    def test_already_elevated_does_not_relaunch(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "win32")
        monkeypatch.setattr(WindowsTrafficController, "is_elevated", lambda self: True)
        fake = mock.Mock()
        monkeypatch.setattr(wc, "_shell_execute_runas", fake)
        result = WindowsTrafficController().relaunch_elevated()
        assert result.success is False and not fake.called

    def test_not_available_off_windows(self, monkeypatch):
        monkeypatch.setattr(sys, "platform", "linux")
        fake = mock.Mock()
        monkeypatch.setattr(wc, "_shell_execute_runas", fake)
        controller = WindowsTrafficController()
        assert controller.can_relaunch_elevated() is False
        assert controller.relaunch_elevated().success is False
        assert not fake.called


class TestLinuxHonesty:
    def test_linux_does_not_pretend_to_relaunch(self):
        controller = LinuxTrafficController()
        assert controller.can_relaunch_elevated() is False
        with mock.patch.object(subprocess, "Popen") as popen, mock.patch.object(subprocess, "run") as run:
            result = controller.relaunch_elevated()
        assert result.success is False
        assert "root" in result.message.lower()
        assert not popen.called and not run.called