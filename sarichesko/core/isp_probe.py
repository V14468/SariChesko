import time
import socket
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from PySide6.QtCore import QThread, Signal

from ..platform import get_monitor
from ..platform.base import NetworkMonitorBase, PingResult


class ISPVerdict(Enum):
    HEALTHY = "healthy"
    LOCAL_CONGESTION = "local_congestion"
    LAST_MILE = "last_mile"
    ISP_DEGRADATION = "isp_degradation"
    ISP_OUTAGE = "isp_outage"
    DNS_ISSUE = "dns_issue"


@dataclass
class ProbeResult:
    level: int
    label: str
    host: str
    ping: PingResult


@dataclass
class ISPDiagnosticResult:
    timestamp: float
    verdict: ISPVerdict
    gateway_latency_ms: Optional[float]
    isp_hop_latency_ms: Optional[float]
    wan_latency_ms: Optional[float]
    dns_ok: bool
    details: str
    probe_results: list[ProbeResult]


class ISPProbeWorker(QThread):
    probe_complete = Signal(object)
    probe_progress = Signal(str, int)
    probe_error = Signal(str)

    def __init__(self):
        super().__init__()
        self._monitor: NetworkMonitorBase = get_monitor()

    def run(self):
        try:
            result = self._run_probes()
            self.probe_complete.emit(result)
        except Exception as e:
            self.probe_error.emit(str(e))

    def _run_probes(self) -> ISPDiagnosticResult:
        probes: list[ProbeResult] = []
        now = time.time()

        # Level 1: Gateway
        self.probe_progress.emit("Probing gateway...", 20)
        gateway = self._monitor.get_default_gateway()
        gw_ping = None
        if gateway:
            gw_ping = self._monitor.ping(gateway, count=3)
            probes.append(ProbeResult(1, "Gateway", gateway, gw_ping))
        else:
            probes.append(ProbeResult(1, "Gateway", "unknown", PingResult("unknown", False, None, "No gateway found")))

        # Level 2: First ISP hop
        self.probe_progress.emit("Tracing ISP first hop...", 40)
        isp_hop_ping = None
        if gateway:
            hops = self._monitor.traceroute("8.8.8.8", max_hops=3)
            isp_host = None
            for h in hops:
                if h.host != gateway and h.host != "* * *" and h.host != "*":
                    isp_host = h.host
                    break
            if isp_host:
                isp_hop_ping = self._monitor.ping(isp_host, count=3)
                probes.append(ProbeResult(2, "ISP First Hop", isp_host, isp_hop_ping))
            else:
                probes.append(ProbeResult(2, "ISP First Hop", "unknown",
                              PingResult("unknown", False, None, "Could not identify ISP hop")))

        # Level 3: WAN
        self.probe_progress.emit("Probing WAN hosts...", 60)
        wan_ping = self._monitor.ping("8.8.8.8", count=3)
        probes.append(ProbeResult(3, "WAN (8.8.8.8)", "8.8.8.8", wan_ping))

        wan2_ping = self._monitor.ping("1.1.1.1", count=3)
        probes.append(ProbeResult(3, "WAN (1.1.1.1)", "1.1.1.1", wan2_ping))

        # Level 4: DNS
        self.probe_progress.emit("Testing DNS resolution...", 80)
        dns_ok = False
        try:
            socket.setdefaulttimeout(5)
            addr = socket.gethostbyname("www.google.com")
            dns_ok = bool(addr)
        except Exception:
            dns_ok = False
        probes.append(ProbeResult(4, "DNS Resolution", "www.google.com",
                      PingResult("dns", dns_ok, None)))

        self.probe_progress.emit("Analyzing results...", 95)

        # Classify
        gw_ok = gw_ping and gw_ping.success if gw_ping else False
        isp_ok = isp_hop_ping and isp_hop_ping.success if isp_hop_ping else None
        wan_ok = wan_ping.success

        gw_lat = gw_ping.latency_ms if gw_ping else None
        isp_lat = isp_hop_ping.latency_ms if isp_hop_ping else None
        wan_lat = wan_ping.latency_ms

        if not gw_ok:
            verdict = ISPVerdict.LOCAL_CONGESTION
            details = "Cannot reach your gateway — the issue is on your local network or router."
        elif isp_ok is False:
            verdict = ISPVerdict.LAST_MILE
            details = "Gateway reachable but ISP first hop is not — likely a last-mile or ISP CPE issue."
        elif not wan_ok:
            verdict = ISPVerdict.ISP_OUTAGE
            details = "ISP hop reachable but WAN hosts are not — ISP upstream outage detected."
        elif not dns_ok:
            verdict = ISPVerdict.DNS_ISSUE
            details = "WAN reachable but DNS resolution failed — DNS resolver issue."
        elif wan_lat and wan_lat > 150:
            verdict = ISPVerdict.ISP_DEGRADATION
            details = f"All hosts reachable but WAN latency is high ({wan_lat:.0f} ms) — possible ISP throttling."
        elif gw_lat and gw_lat > 20:
            verdict = ISPVerdict.LOCAL_CONGESTION
            details = f"Gateway latency is elevated ({gw_lat:.0f} ms) — local network congestion detected."
        else:
            verdict = ISPVerdict.HEALTHY
            details = "All probe targets reachable with normal latency — network is healthy."

        return ISPDiagnosticResult(
            timestamp=now,
            verdict=verdict,
            gateway_latency_ms=gw_lat,
            isp_hop_latency_ms=isp_lat,
            wan_latency_ms=wan_lat,
            dns_ok=dns_ok,
            details=details,
            probe_results=probes,
        )