import pytest
from unittest.mock import MagicMock, patch
from sarichesko.core.isp_probe import (
    ISPVerdict,
    ProbeResult,
    ISPDiagnosticResult,
    ISPProbeWorker,
)
from sarichesko.platform.base import PingResult, TracerouteHop


def test_isp_verdict_enum_values():
    assert ISPVerdict.HEALTHY.value == "healthy"
    assert ISPVerdict.LOCAL_CONGESTION.value == "local_congestion"
    assert ISPVerdict.LAST_MILE.value == "last_mile"
    assert ISPVerdict.ISP_DEGRADATION.value == "isp_degradation"
    assert ISPVerdict.ISP_OUTAGE.value == "isp_outage"
    assert ISPVerdict.DNS_ISSUE.value == "dns_issue"


def test_probe_result_dataclass():
    ping = PingResult(host="192.168.1.1", success=True, latency_ms=1.5)
    probe = ProbeResult(level=1, label="Gateway", host="192.168.1.1", ping=ping)
    assert probe.level == 1
    assert probe.label == "Gateway"
    assert probe.host == "192.168.1.1"
    assert probe.ping.success is True


def test_isp_diagnostic_result_dataclass():
    res = ISPDiagnosticResult(
        timestamp=100.0,
        verdict=ISPVerdict.HEALTHY,
        gateway_latency_ms=1.2,
        isp_hop_latency_ms=10.5,
        wan_latency_ms=25.0,
        dns_ok=True,
        details="All good",
        probe_results=[],
    )
    assert res.verdict == ISPVerdict.HEALTHY
    assert res.dns_ok is True
    assert res.wan_latency_ms == 25.0


def test_probe_gateway_unreachable():
    worker = ISPProbeWorker()
    worker._monitor = MagicMock()
    worker._monitor.get_default_gateway.return_value = "192.168.1.1"
    worker._monitor.ping.side_effect = lambda host, count=3: (
        PingResult(host, False, None, "Unreachable") if host == "192.168.1.1"
        else PingResult(host, True, 20.0)
    )
    worker._monitor.traceroute.return_value = [TracerouteHop(1, "192.168.1.1", 1.0)]

    with patch("socket.gethostbyname", return_value="142.250.190.46"):
        res = worker._run_probes()

    assert res.verdict == ISPVerdict.LOCAL_CONGESTION
    assert "Cannot reach your gateway" in res.details


def test_probe_last_mile_failure():
    worker = ISPProbeWorker()
    worker._monitor = MagicMock()
    worker._monitor.get_default_gateway.return_value = "192.168.1.1"

    def mock_ping(host, count=3):
        if host == "192.168.1.1":
            return PingResult(host, True, 2.0)
        elif host == "10.0.0.1":  # ISP hop
            return PingResult(host, False, None, "Timeout")
        return PingResult(host, True, 25.0)

    worker._monitor.ping.side_effect = mock_ping
    worker._monitor.traceroute.return_value = [
        TracerouteHop(1, "192.168.1.1", 2.0),
        TracerouteHop(2, "10.0.0.1", None),
    ]

    with patch("socket.gethostbyname", return_value="142.250.190.46"):
        res = worker._run_probes()

    assert res.verdict == ISPVerdict.LAST_MILE
    assert "last-mile" in res.details


def test_probe_isp_outage():
    worker = ISPProbeWorker()
    worker._monitor = MagicMock()
    worker._monitor.get_default_gateway.return_value = "192.168.1.1"

    def mock_ping(host, count=3):
        if host in ("192.168.1.1", "10.0.0.1"):
            return PingResult(host, True, 5.0)
        # WAN hosts fail
        return PingResult(host, False, None, "Outage")

    worker._monitor.ping.side_effect = mock_ping
    worker._monitor.traceroute.return_value = [
        TracerouteHop(1, "192.168.1.1", 2.0),
        TracerouteHop(2, "10.0.0.1", 5.0),
    ]

    with patch("socket.gethostbyname", side_effect=Exception("DNS unreachable")):
        res = worker._run_probes()

    assert res.verdict == ISPVerdict.ISP_OUTAGE
    assert "ISP upstream outage" in res.details


def test_probe_dns_issue():
    worker = ISPProbeWorker()
    worker._monitor = MagicMock()
    worker._monitor.get_default_gateway.return_value = "192.168.1.1"
    worker._monitor.ping.return_value = PingResult("host", True, 25.0)
    worker._monitor.traceroute.return_value = [
        TracerouteHop(1, "192.168.1.1", 2.0),
        TracerouteHop(2, "10.0.0.1", 5.0),
    ]

    with patch("socket.gethostbyname", side_effect=Exception("DNS resolution failed")):
        res = worker._run_probes()

    assert res.verdict == ISPVerdict.DNS_ISSUE
    assert "DNS resolver issue" in res.details


def test_probe_isp_degradation():
    worker = ISPProbeWorker()
    worker._monitor = MagicMock()
    worker._monitor.get_default_gateway.return_value = "192.168.1.1"

    def mock_ping(host, count=3):
        if host == "192.168.1.1":
            return PingResult(host, True, 2.0)
        elif host == "10.0.0.1":
            return PingResult(host, True, 10.0)
        return PingResult(host, True, 200.0)  # High WAN latency

    worker._monitor.ping.side_effect = mock_ping
    worker._monitor.traceroute.return_value = [
        TracerouteHop(1, "192.168.1.1", 2.0),
        TracerouteHop(2, "10.0.0.1", 10.0),
    ]

    with patch("socket.gethostbyname", return_value="142.250.190.46"):
        res = worker._run_probes()

    assert res.verdict == ISPVerdict.ISP_DEGRADATION
    assert "WAN latency is high" in res.details


def test_probe_local_gateway_elevated():
    worker = ISPProbeWorker()
    worker._monitor = MagicMock()
    worker._monitor.get_default_gateway.return_value = "192.168.1.1"

    def mock_ping(host, count=3):
        if host == "192.168.1.1":
            return PingResult(host, True, 35.0)  # Elevated gateway > 20ms
        return PingResult(host, True, 45.0)

    worker._monitor.ping.side_effect = mock_ping
    worker._monitor.traceroute.return_value = [
        TracerouteHop(1, "192.168.1.1", 35.0),
        TracerouteHop(2, "10.0.0.1", 40.0),
    ]

    with patch("socket.gethostbyname", return_value="142.250.190.46"):
        res = worker._run_probes()

    assert res.verdict == ISPVerdict.LOCAL_CONGESTION
    assert "Gateway latency is elevated" in res.details


def test_probe_healthy():
    worker = ISPProbeWorker()
    worker._monitor = MagicMock()
    worker._monitor.get_default_gateway.return_value = "192.168.1.1"
    worker._monitor.ping.side_effect = lambda host, count=3: (
        PingResult(host, True, 2.0) if host == "192.168.1.1"
        else PingResult(host, True, 15.0)
    )
    worker._monitor.traceroute.return_value = [
        TracerouteHop(1, "192.168.1.1", 2.0),
        TracerouteHop(2, "10.0.0.1", 5.0),
    ]

    with patch("socket.gethostbyname", return_value="142.250.190.46"):
        res = worker._run_probes()

    assert res.verdict == ISPVerdict.HEALTHY
    assert "network is healthy" in res.details


def test_probe_no_gateway_found():
    worker = ISPProbeWorker()
    worker._monitor = MagicMock()
    worker._monitor.get_default_gateway.return_value = None
    worker._monitor.ping.return_value = PingResult("8.8.8.8", True, 20.0)

    with patch("socket.gethostbyname", return_value="142.250.190.46"):
        res = worker._run_probes()

    assert res.verdict == ISPVerdict.LOCAL_CONGESTION
    assert res.probe_results[0].host == "unknown"


def test_probe_worker_signals():
    worker = ISPProbeWorker()
    complete_mock = MagicMock()
    progress_mock = MagicMock()
    error_mock = MagicMock()

    worker.probe_complete.connect(complete_mock)
    worker.probe_progress.connect(progress_mock)
    worker.probe_error.connect(error_mock)

    with patch.object(worker, "_run_probes", return_value="dummy_result"):
        worker.run()

    complete_mock.assert_called_once_with("dummy_result")
    error_mock.assert_not_called()


def test_probe_worker_error_signal():
    worker = ISPProbeWorker()
    complete_mock = MagicMock()
    error_mock = MagicMock()

    worker.probe_complete.connect(complete_mock)
    worker.probe_error.connect(error_mock)

    with patch.object(worker, "_run_probes", side_effect=RuntimeError("Probe crash")):
        worker.run()

    complete_mock.assert_not_called()
    error_mock.assert_called_once_with("Probe crash")
