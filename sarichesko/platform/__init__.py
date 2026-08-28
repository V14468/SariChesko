import sys
from .base import NetworkMonitorBase, TrafficControllerBase


def get_monitor() -> NetworkMonitorBase:
    if sys.platform == "win32":
        from .windows.monitor import WindowsNetworkMonitor
        return WindowsNetworkMonitor()
    else:
        from .linux.monitor import LinuxNetworkMonitor
        return LinuxNetworkMonitor()


def get_controller() -> TrafficControllerBase:
    if sys.platform == "win32":
        from .windows.controller import WindowsTrafficController
        return WindowsTrafficController()
    else:
        from .linux.controller import LinuxTrafficController
        return LinuxTrafficController()