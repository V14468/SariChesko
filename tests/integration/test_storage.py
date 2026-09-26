import sqlite3
import pytest
from sarichesko.storage.db import init_db
from sarichesko.storage.repository import Repository
from sarichesko.storage.models import (
    Session,
    Measurement,
    Baseline,
    ISPDiagnostic,
    DiagnosticRun,
    AppliedPolicy,
    SimulationResult,
)


@pytest.fixture
def repo():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return Repository(conn)


def test_models_default_values():
    s = Session(id="s-def", started_at=100.0)
    assert s.mode == "real"
    assert s.ended_at is None
    assert s.interface is None

    m = Measurement(session_id="s-def", timestamp=100.0)
    assert m.bandwidth_mbps == 0.0
    assert m.latency_ms == 0.0
    assert m.packet_loss_pct == 0.0

    b = Baseline(interface="eth0", measured_at=100.0)
    assert b.latency_mean_ms == 0.0
    assert b.loss_mean_pct == 0.0


def test_session_lifecycle(repo):
    s = Session(id="sess-1", started_at=100.0, mode="real", interface="eth0")
    repo.save_session(s)

    iface = repo.get_session_interface("sess-1")
    assert iface == "eth0"
    assert repo.get_session_interface("unknown") is None

    repo.end_session("sess-1", 200.0)
    # Re-saving session overwrites/updates
    s.ended_at = 200.0
    repo.save_session(s)


def test_end_session_nonexistent(repo):
    # Should execute without crashing
    repo.end_session("non-existent-sess", 500.0)


def test_measurements_crud(repo):
    s = Session(id="sess-m", started_at=100.0)
    repo.save_session(s)

    for i in range(5):
        m = Measurement(
            session_id="sess-m",
            timestamp=100.0 + i,
            bandwidth_mbps=50.0 + i,
            latency_ms=10.0 + i,
            jitter_ms=1.0,
            packet_loss_pct=0.0,
            utilization_pct=40.0,
            queue_delay_ms=0.0,
        )
        repo.save_measurement(m)

    recent = repo.get_recent_measurements("sess-m", limit=3)
    assert len(recent) == 3
    # Ordered by timestamp DESC
    assert recent[0]["timestamp"] == 104.0
    assert recent[1]["timestamp"] == 103.0
    assert recent[2]["timestamp"] == 102.0


def test_measurements_empty(repo):
    assert repo.get_recent_measurements("no-such-session") == []


def test_baseline_crud(repo):
    base = Baseline(
        interface="wlan0",
        measured_at=500.0,
        latency_mean_ms=15.5,
        latency_stddev_ms=2.1,
        loss_mean_pct=0.5,
        bandwidth_mean_mbps=85.0,
        jitter_mean_ms=1.2,
    )
    repo.save_baseline(base)

    fetched = repo.get_baseline("wlan0")
    assert fetched is not None
    assert fetched.interface == "wlan0"
    assert fetched.latency_mean_ms == 15.5
    assert fetched.bandwidth_mean_mbps == 85.0

    assert repo.get_baseline("non_existent") is None


def test_isp_diagnostic_save(repo):
    s = Session(id="sess-isp", started_at=100.0)
    repo.save_session(s)

    diag = ISPDiagnostic(
        session_id="sess-isp",
        timestamp=105.0,
        verdict="healthy",
        details="All hosts reachable",
        gateway_ms=2.1,
        isp_hop_ms=8.4,
        wan_ms=22.0,
        dns_ok=True,
    )
    repo.save_isp_diagnostic(diag)


def test_diagnostic_runs_crud(repo):
    s = Session(id="sess-diag", started_at=100.0)
    repo.save_session(s)

    run = DiagnosticRun(
        id="run-1",
        session_id="sess-diag",
        timestamp=110.0,
        congestion_score=42.0,
        severity="MODERATE",
        dominant_signal="latency_delta",
        isp_verdict="healthy",
        recommended_algo="CoDel",
        recommendation_reason="Mitigates bufferbloat",
        confidence="HIGH",
    )
    repo.save_diagnostic_run(run)

    runs = repo.get_diagnostic_runs(limit=10)
    assert len(runs) == 1
    assert runs[0]["id"] == "run-1"
    assert runs[0]["congestion_score"] == 42.0
    assert runs[0]["recommended_algo"] == "CoDel"


def test_applied_policies_crud(repo):
    policy = AppliedPolicy(
        id="pol-1",
        diagnostic_id="run-1",
        timestamp=120.0,
        interface="eth0",
        algorithm="Token Bucket",
        parameters='{"rate_bps": 10000000}',
        snapshot_before="default",
        score_before=65.0,
        score_after=20.0,
        verdict="IMPROVED",
        rolled_back_at=None,
    )
    repo.save_applied_policy(policy)

    policies = repo.get_applied_policies(limit=10)
    assert len(policies) == 1
    assert policies[0]["id"] == "pol-1"
    assert policies[0]["algorithm"] == "Token Bucket"
    assert policies[0]["verdict"] == "IMPROVED"


def test_simulation_results_crud(repo):
    sim = SimulationResult(
        id="sim-1",
        timestamp=130.0,
        scenario="bursty_traffic",
        algorithm="Token Bucket",
        engine_used="python_sim",
        parameters='{"rate": 100}',
        throughput_mbps=94.5,
        avg_latency_ms=12.2,
        loss_pct=0.1,
        fairness_index=0.98,
        metrics_detail='{"points": [1, 2, 3]}',
    )
    repo.save_simulation_result(sim)

    results = repo.get_simulation_results(limit=10)
    assert len(results) == 1
    assert results[0]["id"] == "sim-1"
    assert results[0]["throughput_mbps"] == 94.5

    latest = repo.get_latest_simulation_result("bursty_traffic", "Token Bucket")
    assert latest is not None
    assert latest["id"] == "sim-1"

    non_existent = repo.get_latest_simulation_result("unknown", "none")
    assert non_existent is None


def test_settings_storage(repo):
    assert repo.get_setting("custom_key", "default_val") == "default_val"

    repo.set_setting("custom_key", "stored_val")
    assert repo.get_setting("custom_key", "default_val") == "stored_val"

    repo.set_setting("custom_key", "updated_val")
    assert repo.get_setting("custom_key") == "updated_val"


# ── clear_history / clear_baselines / get_history_counts ──────────────

def _populate_all_tables(repo):
    """Insert one row into every data table for testing bulk operations."""
    repo.save_session(Session(id="s1", started_at=100.0, interface="eth0"))
    repo.save_measurement(Measurement(
        session_id="s1", timestamp=101.0, bandwidth_mbps=50.0, latency_ms=10.0,
        jitter_ms=1.0, packet_loss_pct=0.0, utilization_pct=30.0, queue_delay_ms=0.0,
    ))
    repo.save_baseline(Baseline(
        interface="eth0", measured_at=90.0,
        latency_mean_ms=10.0, latency_stddev_ms=1.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=1.0,
    ))
    repo.save_isp_diagnostic(ISPDiagnostic(
        session_id="s1", timestamp=102.0, verdict="healthy",
        details="ok", gateway_ms=2.0, isp_hop_ms=5.0, wan_ms=20.0, dns_ok=True,
    ))
    repo.save_diagnostic_run(DiagnosticRun(
        id="dr1", session_id="s1", timestamp=103.0, congestion_score=25.0,
        severity="MILD", dominant_signal="latency_delta", isp_verdict="healthy",
        recommended_algo="CoDel", recommendation_reason="test", confidence="HIGH",
    ))
    repo.save_applied_policy(AppliedPolicy(
        id="ap1", diagnostic_id="dr1", timestamp=104.0, interface="eth0",
        algorithm="CoDel", parameters="{}", snapshot_before="snap",
        score_before=25.0, score_after=10.0, verdict="improved",
    ))
    repo.save_simulation_result(SimulationResult(
        id="sr1", timestamp=105.0, scenario="bursty_traffic", algorithm="CoDel",
        engine_used="python_sim", parameters="{}", throughput_mbps=90.0,
        avg_latency_ms=8.0, loss_pct=0.1, fairness_index=0.99, metrics_detail="{}",
    ))
    repo.set_setting("test_key", "test_val")


def test_get_history_counts(repo):
    counts = repo.get_history_counts()
    assert all(v == 0 for v in counts.values())
    assert set(counts.keys()) == {
        "sessions", "measurements", "diagnostic_runs",
        "simulation_results", "applied_policies", "baselines",
    }

    _populate_all_tables(repo)
    counts = repo.get_history_counts()
    assert counts["sessions"] == 1
    assert counts["measurements"] == 1
    assert counts["diagnostic_runs"] == 1
    assert counts["simulation_results"] == 1
    assert counts["applied_policies"] == 1
    assert counts["baselines"] == 1


def test_clear_history_preserves_baselines_and_settings(repo):
    _populate_all_tables(repo)
    repo.clear_history()

    counts = repo.get_history_counts()
    assert counts["sessions"] == 0
    assert counts["measurements"] == 0
    assert counts["diagnostic_runs"] == 0
    assert counts["simulation_results"] == 0
    assert counts["applied_policies"] == 0
    # Baselines must survive
    assert counts["baselines"] == 1
    # Settings must survive
    assert repo.get_setting("test_key") == "test_val"


def test_clear_baselines_only(repo):
    _populate_all_tables(repo)
    repo.clear_baselines()

    counts = repo.get_history_counts()
    assert counts["baselines"] == 0
    # Everything else must survive
    assert counts["sessions"] == 1
    assert counts["measurements"] == 1
    assert counts["diagnostic_runs"] == 1


def test_clear_history_on_empty_db(repo):
    """Must not crash when there's nothing to delete."""
    repo.clear_history()
    counts = repo.get_history_counts()
    assert all(v == 0 for v in counts.values())


def test_clear_baselines_on_empty_db(repo):
    """Must not crash when there are no baselines."""
    repo.clear_baselines()
    assert repo.get_baseline("eth0") is None
