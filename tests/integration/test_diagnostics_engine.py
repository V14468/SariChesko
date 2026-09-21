import sqlite3
import pytest
from unittest.mock import MagicMock, patch
from sarichesko.core.diagnostics_engine import DiagnosticsWorker, DiagnosticResult
from sarichesko.core.congestion_scorer import CongestionScore
from sarichesko.core.isp_probe import ISPVerdict, ISPDiagnosticResult
from sarichesko.core.recommendation_engine import TrafficProfile, Recommendation, Algorithm
from sarichesko.storage.models import Measurement
from sarichesko.platform.base import InterfaceStats, PingResult


def test_diagnostic_result_dataclass():
    score = CongestionScore(10.0, "NONE", {}, "none", False, "STABLE")
    isp = ISPDiagnosticResult(100.0, ISPVerdict.HEALTHY, 1.0, 5.0, 15.0, True, "ok", [])
    profile = TrafficProfile(False, "HIGH", False, 0.0, 5.0, "none")
    rec = Recommendation(Algorithm.CODEL, {}, "Test", "HIGH", ["Act"])

    diag = DiagnosticResult(
        id="d-1",
        timestamp=100.0,
        congestion_score=score,
        isp_result=isp,
        traffic_profile=profile,
        recommendation=rec,
        measurements=[],
    )
    assert diag.id == "d-1"
    assert diag.congestion_score.score == 10.0
    assert diag.recommendation.algo == Algorithm.CODEL


def test_diagnostics_worker_init():
    worker = DiagnosticsWorker(interface="eth0", session_id="test-session")
    assert worker._iface == "eth0"
    assert worker._session_id == "test-session"


def test_diagnostics_worker_run_success(tmp_path):
    worker = DiagnosticsWorker(interface="eth0", session_id="test-session")

    # Mock monitor
    mock_mon = MagicMock()
    cur_time = [100.0]

    def mock_stats(iface):
        cur_time[0] += 0.5
        return InterfaceStats(
            timestamp=cur_time[0],
            iface=iface,
            bytes_sent=1000,
            bytes_recv=1000,
            packets_sent=10,
            packets_recv=10,
            errin=0,
            errout=0,
            dropin=0,
            dropout=0,
        )

    mock_mon.get_stats.side_effect = mock_stats
    mock_mon.ping.return_value = PingResult("8.8.8.8", True, 20.0)
    mock_mon.get_default_gateway.return_value = "192.168.1.1"
    mock_mon.traceroute.return_value = []
    worker._monitor = mock_mon

    # Temporary SQLite database
    db_file = tmp_path / "test.db"

    def get_test_conn():
        c = sqlite3.connect(str(db_file), check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    progress_calls = []
    results = []
    errors = []

    worker.progress.connect(lambda msg, pct: progress_calls.append((msg, pct)))
    worker.complete.connect(lambda res: results.append(res))
    worker.error.connect(lambda err: errors.append(err))

    with patch("sarichesko.core.diagnostics_engine.get_connection", side_effect=get_test_conn):
        with patch("time.sleep", return_value=None):
            with patch("socket.gethostbyname", return_value="142.250.190.46"):
                worker.run()

    assert len(errors) == 0
    assert len(results) == 1
    diag_res = results[0]
    assert isinstance(diag_res, DiagnosticResult)
    assert len(diag_res.measurements) == 10
    assert len(progress_calls) > 0


def test_diagnostics_worker_error_handling():
    worker = DiagnosticsWorker(interface="eth0")
    error_mock = MagicMock()
    worker.error.connect(error_mock)

    with patch("sarichesko.core.diagnostics_engine.get_connection", side_effect=RuntimeError("DB Connection Failed")):
        worker.run()

    error_mock.assert_called_once()
    assert "DB Connection Failed" in error_mock.call_args[0][0]
