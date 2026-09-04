import subprocess
import time
import re
from typing import Optional

import psutil

from ..base import (
    NetworkMonitorBase, InterfaceInfo, InterfaceStats,
    PingResult, TracerouteHop,
)


class WindowsNetworkMonitor(NetworkMonitorBase):

    def get_interfaces(self) -> list[InterfaceInfo]:
        result = []
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        for name, st in stats.items():
            mac = ""
            if name in addrs:
                for a in addrs[name]:
                    if a.family.name == "AF_LINK":
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
                ["ping", "-n", str(count), "-w", "2000", host],
                capture_output=True, text=True, timeout=30,
            )
            match = re.search(r"Average\s*=\s*(\d+)\s*ms", out.stdout)
            if match:
                return PingResult(host=host, success=True, latency_ms=float(match.group(1)))
            if "Reply from" in out.stdout:
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
                ["tracert", "-d", "-h", str(max_hops), "-w", "2000", host],
                capture_output=True, text=True, timeout=60,
            )
            for line in out.stdout.splitlines():
                match = re.match(
                    r"\s*(\d+)\s+(?:(\d+)\s*ms|\*)\s+(?:(\d+)\s*ms|\*)\s+(?:(\d+)\s*ms|\*)\s+([\d.]+|\*)",
                    line,
                )
                if match:
                    hop_num = int(match.group(1))
                    latencies = [float(x) for x in [match.group(2), match.group(3), match.group(4)] if x]
                    avg = sum(latencies) / len(latencies) if latencies else None
                    hop_host = match.group(5) if match.group(5) != "*" else "* * *"
                    hops.append(TracerouteHop(hop=hop_num, host=hop_host, latency_ms=avg))
        except (subprocess.TimeoutExpired, Exception):
            pass
        return hops

    def get_default_gateway(self) -> Optional[str]:
        # Method 1: Use psutil's net_if_addrs + WMI-style approach isn't available,
        # so parse ipconfig with broader matching
        try:
            out = subprocess.run(
                ["ipconfig"], capture_output=True, text=True, timeout=10,
            )
                # Match various ipconfig gateway formats across locales
            for line in out.stdout.splitlines():
                line_stripped = line.strip()
                    # English: "Default Gateway . . . : 192.168.x.x"
                    # Also handles lines that just have an IP after the gateway label
                if "gateway" in line_stripped.lower() or "puerta" in line_stripped.lower() or "gateway" in line_stripped.lower():
                    match = re.search(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})", line_stripped)
                    if match:
                        return match.group(1)
        except Exception:
            pass

            # Method 2: Use 'route print' as fallback
        try:
            out = subprocess.run(
                ["route", "print", "0.0.0.0"], capture_output=True, text=True, timeout=10,
            )
            for line in out.stdout.splitlines():
                parts = line.split()
                if len(parts) >= 3 and parts[0] == "0.0.0.0":
                    gw = parts[2]
                    if re.match(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", gw):
                        return gw
        except Exception:
            pass

        return None

    def get_dns_servers(self) -> list[str]:
        servers = []
        try:
            out = subprocess.run(
                ["ipconfig", "/all"], capture_output=True, text=True, timeout=10,
            )
            for match in re.finditer(r"DNS Servers[\s.]*:\s*([\d.]+)", out.stdout):
                servers.append(match.group(1))
        except Exception:
            pass
        return servers