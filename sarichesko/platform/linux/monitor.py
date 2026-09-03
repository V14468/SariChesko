import subprocess
import time
import re
from typing import Optional

import psutil

from ..base import (
    NetworkMonitorBase, InterfaceInfo, InterfaceStats,
    PingResult, TracerouteHop,
)


class LinuxNetworkMonitor(NetworkMonitorBase):

    def get_interfaces(self) -> list[InterfaceInfo]:
        result = []
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        for name, st in stats.items():
            mac = ""
            if name in addrs:
                for a in addrs[name]:
                    if a.family.name == "AF_PACKET":
                        mac = a.address
                        break
            result.append(InterfaceInfo(
                name=name,
                display_name=name,
                is_up=st.isup,
                speed_mbps=st.speed if st.speed > 0 else None,
                mac=mac,
            ))
        return result

    def get_stats(self, iface: str) -> InterfaceStats:
        counters = psutil.net_io_counters(pernic=True)
        if iface not in counters:
            raise ValueError(f"Interface '{iface}' not found")
        c = counters[iface]
        return InterfaceStats(
            timestamp=time.time(),
            iface=iface,
            bytes_sent=c.bytes_sent,
            bytes_recv=c.bytes_recv,
            packets_sent=c.packets_sent,
            packets_recv=c.packets_recv,
            errin=c.errin,
            errout=c.errout,
            dropin=c.dropin,
            dropout=c.dropout,
        )

    def ping(self, host: str, count: int = 4) -> PingResult:
        try:
            out = subprocess.run(
                ["ping", "-c", str(count), "-W", "2", host],
                capture_output=True, text=True, timeout=30,
            )
            match = re.search(r"rtt min/avg/max/mdev = [\d.]+/([\d.]+)/", out.stdout)
            if match:
                return PingResult(host=host, success=True, latency_ms=float(match.group(1)))
            if "bytes from" in out.stdout:
                return PingResult(host=host, success=True, latency_ms=None)
            return PingResult(host=host, success=False, latency_ms=None, error=out.stdout.strip()[-200:])
        except subprocess.TimeoutExpired:
            return PingResult(host=host, success=False, latency_ms=None, error="Ping timed out")
        except Exception as e:
            return PingResult(host=host, success=False, latency_ms=None, error=str(e))

    def traceroute(self, host: str, max_hops: int = 5) -> list[TracerouteHop]:
        hops = []
        try:
            out = subprocess.run(
                ["traceroute", "-n", "-m", str(max_hops), "-w", "2", host],
                capture_output=True, text=True, timeout=60,
            )
            for line in out.stdout.splitlines():
                match = re.match(r"\s*(\d+)\s+([\d.]+|\*)\s+([\d.]+)\s*ms", line)
                if match:
                    hop_num = int(match.group(1))
                    hop_host = match.group(2)
                    lat = float(match.group(3)) if match.group(2) != "*" else None
                    hops.append(TracerouteHop(hop=hop_num, host=hop_host, latency_ms=lat))
        except (subprocess.TimeoutExpired, Exception):
            pass
        return hops

    def get_default_gateway(self) -> Optional[str]:
        try:
            out = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True, text=True, timeout=10,
            )
            match = re.search(r"default via ([\d.]+)", out.stdout)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def get_dns_servers(self) -> list[str]:
        servers = []
        try:
            with open("/etc/resolv.conf", "r") as f:
                for line in f:
                    match = re.match(r"nameserver\s+([\d.]+)", line)
                    if match:
                        servers.append(match.group(1))
        except Exception:
            pass
        return servers