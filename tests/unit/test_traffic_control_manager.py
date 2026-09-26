"""Tests for sarichesko.core.traffic_control_manager — the safety-critical
module that applies real network-configuration changes and reverts them.

Every test uses mock/fake controllers and an in-memory (or tmp_path) SQLite
database. Nothing here touches a real network interface, runs PowerShell, or
invokes ``tc``.
"""
import json
import sqlite3
import time
import uuid
from unittest.mock import MagicMock, patch, call

import pytest

from sarichesko.core.traffic_control_manager import (
    IMPROVEMENT_THRESHOLD,
    ApplyFixReport,
    ApplyFixWorker,
    RollbackWorker,
    verdict_for,
)
from sarichesko.core.recommendation_engine import Algorithm
from sarichesko.core.diagnostics_engine import DiagnosticResult
from sarichesko.core.congestion_scorer import CongestionScore
from sarichesko.core.isp_probe import ISPDiagnosticResult, ISPVerdict, ProbeResult
from sarichesko.platform.base import ApplyResult, ConfigSnapshot, TrafficControllerBase, PingResult
from sarichesko.storage.db import init_db
from sarichesko.storage.models import AppliedPolicy, Measurement
from sarichesko.storage.repository import Repository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_shared_db_counter = 0


def _make_shared_conn(db_name: str = "default") -> sqlite3.Connection:
    """Return a connection to a named in-memory SQLite DB with the full
    SariChesko schema.  Multiple connections to the same ``db_name`` share
    state, which lets our assertion code read what the production code wrote
    even after the production code closes its own handle."""
    conn = sqlite3.connect(f"file:{db_name}?mode=memory&cache=shared",
                           uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def _shared_conn_factory(db_name: str):
    """Return a callable that produces new handles to the same named
    in-memory SQLite database — one for the production code (which will
    close it) and one for test assertions (which stays open)."""
    def factory():
        return _make_shared_conn(db_name)
    return factory


def _fake_diagnostic_result(score: float = 30.0,
                             latency_ms: float = 15.0,
                             loss_pct: float = 1.0) -> DiagnosticResult:
    """Build a lightweight DiagnosticResult suitable for verification stubs."""
    from sarichesko.core.recommendation_engine import Recommendation, TrafficProfile

    cong = CongestionScore(
        score=score, severity="MILD", signals={},
        dominant_signal="latency_delta", is_persistent=False, trend="STABLE",
    )
    isp = ISPDiagnosticResult(
        timestamp=time.time(),
        verdict=ISPVerdict.HEALTHY,
        gateway_latency_ms=1.0,
        isp_hop_latency_ms=5.0,
        wan_latency_ms=10.0,
        dns_ok=True,
        details="ok",
        probe_results=[
            ProbeResult(level=0, label="Gateway", host="192.168.1.1",
                        ping=PingResult(host="192.168.1.1", success=True, latency_ms=1.0)),
        ],
    )
    profile = TrafficProfile(
        is_bursty=False, burst_tolerance="LOW",
        needs_smooth_output=False, queue_growth_rate=0.0,
        sojourn_time_ms=0.0, dominant_signal="none",
    )
    rec = Recommendation(
        algo=None, parameters={}, reason="ok", confidence="HIGH", actions=[],
    )
    measurements = [
        Measurement(session_id="s1", timestamp=time.time(),
                    latency_ms=latency_ms, packet_loss_pct=loss_pct),
    ]
    return DiagnosticResult(
        id=str(uuid.uuid4()), timestamp=time.time(),
        congestion_score=cong, isp_result=isp,
        traffic_profile=profile, recommendation=rec,
        measurements=measurements,
    )


class FakeController(TrafficControllerBase):
    """A concrete in-memory controller that never calls any OS subprocess."""

    def __init__(self, apply_result: ApplyResult | None = None):
        self._apply_result = apply_result or ApplyResult(success=True, message="Applied OK")
        self._last_snapshot = None
        self._restored = False

    def is_supported(self) -> bool:
        return True

    def requires_elevation(self) -> bool:
        return False

    def is_elevated(self) -> bool:
        return False

    def save_snapshot(self, iface: str) -> ConfigSnapshot:
        self._last_snapshot = ConfigSnapshot(interface=iface, raw="fake-snapshot-data")
        return self._last_snapshot

    def restore_snapshot(self, snapshot: ConfigSnapshot) -> ApplyResult:
        self._restored = True
        return ApplyResult(success=True, message="Restored.")

    def apply_leaky_bucket(self, iface, rate_bps, burst_bytes) -> ApplyResult:
        return self._apply_result

    def apply_token_bucket(self, iface, rate_bps, burst_bytes, latency_ms) -> ApplyResult:
        return self._apply_result

    def apply_red(self, iface, min_th, max_th, max_p, limit) -> ApplyResult:
        return self._apply_result

    def apply_codel(self, iface, target_ms, interval_ms, limit) -> ApplyResult:
        return self._apply_result

    def remove_policy(self, iface) -> ApplyResult:
        return ApplyResult(success=True, message="Removed.")


def _build_worker(cls, attrs: dict):
    """Create a QThread-based worker without calling QThread.__init__,
    then attach mock signals whose ``.emit()`` can be captured."""
    worker = cls.__new__(cls)
    for k, v in attrs.items():
        setattr(worker, k, v)
    worker.progress = MagicMock()
    worker.complete = MagicMock()
    worker.error = MagicMock()
    return worker


# ===================================================================
# 1  verdict_for() — pure boundary tests
# ===================================================================

class TestVerdictFor:
    """Requirement 1: boundary tests for the scoring-delta function,
    including the zero-before-score guard against division by zero."""

    def test_clear_improvement(self):
        # 50 -> 30 = 40% decrease, well above 10% threshold
        assert verdict_for(50.0, 30.0) == "improved"

    def test_exactly_at_improvement_threshold(self):
        # delta = 0.10 exactly
        before = 100.0
        after = before * (1 - IMPROVEMENT_THRESHOLD)  # 90.0
        assert verdict_for(before, after) == "improved"

    def test_just_below_improvement_threshold(self):
        before = 100.0
        after = before * (1 - IMPROVEMENT_THRESHOLD) + 0.01  # 90.01
        assert verdict_for(before, after) == "no_change"

    def test_clear_worsening(self):
        # 50 -> 70 = -40% (negative delta)
        assert verdict_for(50.0, 70.0) == "worse"

    def test_exactly_at_worsening_threshold(self):
        before = 100.0
        after = before * (1 + IMPROVEMENT_THRESHOLD)  # 110.0
        assert verdict_for(before, after) == "worse"

    def test_just_inside_no_change_band(self):
        before = 100.0
        # after = 109.99 → delta = (100-109.99)/100 = -0.0999 > -0.10
        after = before * (1 + IMPROVEMENT_THRESHOLD) - 0.01
        assert verdict_for(before, after) == "no_change"

    def test_identical_scores(self):
        assert verdict_for(42.0, 42.0) == "no_change"

    def test_zero_before_score_no_divide_by_zero(self):
        """score_before == 0 must not raise ZeroDivisionError."""
        assert verdict_for(0.0, 50.0) == "no_change"

    def test_negative_before_score_treated_as_no_change(self):
        """Negative scores (shouldn't occur, but guard anyway)."""
        assert verdict_for(-5.0, 50.0) == "no_change"

    def test_both_zero(self):
        assert verdict_for(0.0, 0.0) == "no_change"


# ===================================================================
# 2  ApplyFixWorker — failure path
# ===================================================================

class TestApplyFixWorkerFailurePath:
    """Requirement 2: if the platform controller's apply_* reports failure,
    NOTHING gets written to applied_policies and the report says applied=False."""

    def test_failure_emits_report_applied_false(self):
        """Controller says 'no' → report.applied is False, policy_id is None."""
        fail_ctrl = FakeController(ApplyResult(success=False, message="Access denied"))

        worker = _build_worker(ApplyFixWorker, {
            "_iface": "eth0",
            "_algo": Algorithm.LEAKY_BUCKET,
            "_parameters": {"rate_bps": 10_000_000, "burst_bytes": 32768},
            "_score_before": 55.0,
            "_diagnostic_id": "diag-1",
            "_latency_before_ms": 20.0,
            "_loss_before_pct": 2.0,
            "_controller": fail_ctrl,
        })

        with patch("sarichesko.core.traffic_control_manager.get_connection",
                    _shared_conn_factory("fail_emit")), \
             patch("sarichesko.core.traffic_control_manager.init_db"):
            worker.run()

        worker.complete.emit.assert_called_once()
        report: ApplyFixReport = worker.complete.emit.call_args[0][0]
        assert report.applied is False
        assert report.policy_id is None
        assert "Access denied" in report.apply_message

    def test_failure_writes_nothing_to_db(self):
        """On apply failure, the applied_policies table must stay empty."""
        db_name = f"fail_nodb_{uuid.uuid4().hex[:8]}"
        assertion_conn = _make_shared_conn(db_name)
        fail_ctrl = FakeController(ApplyResult(success=False, message="Nope"))

        worker = _build_worker(ApplyFixWorker, {
            "_iface": "eth0",
            "_algo": Algorithm.TOKEN_BUCKET,
            "_parameters": {"rate_bps": 5_000_000, "burst_bytes": 65536, "latency_ms": 50},
            "_score_before": 40.0,
            "_diagnostic_id": "diag-2",
            "_latency_before_ms": None,
            "_loss_before_pct": None,
            "_controller": fail_ctrl,
        })

        with patch("sarichesko.core.traffic_control_manager.get_connection",
                    _shared_conn_factory(db_name)), \
             patch("sarichesko.core.traffic_control_manager.init_db"):
            worker.run()

        repo = Repository(assertion_conn)
        rows = repo.get_applied_policies(limit=100)
        assert len(rows) == 0
        assertion_conn.close()


# ===================================================================
# 3  ApplyFixWorker — success path
# ===================================================================

class TestApplyFixWorkerSuccessPath:
    """Requirement 3: on success the worker must (a) save a snapshot,
    (b) apply, (c) persist an applied_policies row, (d) re-verify via
    a real re-measurement, (e) update that row with after-score and verdict,
    (f) the emitted report must match what got persisted."""

    def _run_successful_worker(self, score_before=60.0, score_after=30.0):
        """Helper that runs a fully mocked successful apply-fix cycle."""
        db_name = f"success_{uuid.uuid4().hex[:8]}"
        assertion_conn = _make_shared_conn(db_name)
        ctrl = FakeController(ApplyResult(success=True, message="Applied OK"))

        worker = _build_worker(ApplyFixWorker, {
            "_iface": "eth0",
            "_algo": Algorithm.LEAKY_BUCKET,
            "_parameters": {"rate_bps": 8_000_000, "burst_bytes": 32768},
            "_score_before": score_before,
            "_diagnostic_id": "diag-100",
            "_latency_before_ms": 25.0,
            "_loss_before_pct": 3.0,
            "_controller": ctrl,
        })

        diag_result = _fake_diagnostic_result(score=score_after, latency_ms=10.0, loss_pct=0.5)

        def fake_run_verification(self_inner):
            return diag_result, None

        with patch("sarichesko.core.traffic_control_manager.get_connection",
                    _shared_conn_factory(db_name)), \
             patch("sarichesko.core.traffic_control_manager.init_db"), \
             patch.object(ApplyFixWorker, "_run_verification", fake_run_verification):
            worker.run()

        worker.complete.emit.assert_called_once()
        report = worker.complete.emit.call_args[0][0]
        return report, assertion_conn, ctrl

    def test_snapshot_saved_before_apply(self):
        report, conn, ctrl = self._run_successful_worker()
        # FakeController records the snapshot it created
        assert ctrl._last_snapshot is not None
        assert ctrl._last_snapshot.interface == "eth0"
        # Report also carries the snapshot
        assert report.snapshot is not None
        assert report.snapshot.raw == "fake-snapshot-data"
        conn.close()

    def test_applied_policies_row_persisted(self):
        report, conn, ctrl = self._run_successful_worker()
        repo = Repository(conn)
        rows = repo.get_applied_policies(limit=100)
        assert len(rows) == 1
        conn.close()

    def test_row_has_correct_before_and_after_scores(self):
        report, conn, ctrl = self._run_successful_worker(score_before=60.0, score_after=30.0)
        repo = Repository(conn)
        row = repo.get_applied_policies(limit=1)[0]
        assert row["score_before"] == 60.0
        assert row["score_after"] == 30.0
        conn.close()

    def test_row_has_correct_verdict(self):
        report, conn, ctrl = self._run_successful_worker(score_before=60.0, score_after=30.0)
        repo = Repository(conn)
        row = repo.get_applied_policies(limit=1)[0]
        expected_verdict = verdict_for(60.0, 30.0)
        assert row["verdict"] == expected_verdict
        assert expected_verdict == "improved"
        conn.close()

    def test_report_matches_db_row(self):
        """UI and DB must never disagree — requirement (f)."""
        report, conn, ctrl = self._run_successful_worker(score_before=60.0, score_after=30.0)
        repo = Repository(conn)
        row = repo.get_applied_policies(limit=1)[0]

        assert report.applied is True
        assert report.policy_id == row["id"]
        assert report.score_before == row["score_before"]
        assert report.score_after == row["score_after"]
        assert report.verdict == row["verdict"]
        conn.close()

    def test_report_applied_true(self):
        report, conn, ctrl = self._run_successful_worker()
        assert report.applied is True
        assert report.policy_id is not None
        conn.close()

    def test_worsened_verdict_persisted(self):
        """If the fix makes things worse, the verdict must say so, not lie."""
        report, conn, ctrl = self._run_successful_worker(score_before=30.0, score_after=60.0)
        repo = Repository(conn)
        row = repo.get_applied_policies(limit=1)[0]
        assert row["verdict"] == "worse"
        assert report.verdict == "worse"
        conn.close()


# ===================================================================
# 4  Verification-failure honesty
# ===================================================================

class TestVerificationFailureHonesty:
    """Requirement 4: if the post-apply re-measurement itself fails, the
    report must NOT invent a fake success. score_after=None, verdict=None."""

    def _run_with_verification_failure(self, error_msg="measurement timeout"):
        db_name = f"verfail_{uuid.uuid4().hex[:8]}"
        assertion_conn = _make_shared_conn(db_name)
        ctrl = FakeController(ApplyResult(success=True, message="Applied OK"))

        worker = _build_worker(ApplyFixWorker, {
            "_iface": "eth0",
            "_algo": Algorithm.CODEL,
            "_parameters": {"target_ms": 5, "interval_ms": 100, "limit": 1024},
            "_score_before": 70.0,
            "_diagnostic_id": "diag-v",
            "_latency_before_ms": 30.0,
            "_loss_before_pct": 5.0,
            "_controller": ctrl,
        })

        def fake_run_verification_error(self_inner):
            return None, error_msg

        with patch("sarichesko.core.traffic_control_manager.get_connection",
                    _shared_conn_factory(db_name)), \
             patch("sarichesko.core.traffic_control_manager.init_db"), \
             patch.object(ApplyFixWorker, "_run_verification", fake_run_verification_error):
            worker.run()

        worker.complete.emit.assert_called_once()
        report = worker.complete.emit.call_args[0][0]
        assertion_conn.close()
        return report

    def test_verification_failure_score_after_is_none(self):
        report = self._run_with_verification_failure()
        assert report.score_after is None

    def test_verification_failure_verdict_is_none(self):
        report = self._run_with_verification_failure()
        assert report.verdict is None

    def test_verification_failure_still_applied_true(self):
        """The fix WAS applied — honesty means saying so, not hiding the apply."""
        report = self._run_with_verification_failure()
        assert report.applied is True

    def test_verification_failure_message_mentions_failure(self):
        report = self._run_with_verification_failure(error_msg="ping timed out")
        assert "verification" in report.apply_message.lower() or \
               "Verification" in report.apply_message

    def test_verification_returns_none_result_no_error(self):
        """Edge case: result is None but no error string either."""
        db_name = f"ver_none_{uuid.uuid4().hex[:8]}"
        assertion_conn = _make_shared_conn(db_name)
        ctrl = FakeController(ApplyResult(success=True, message="Applied"))

        worker = _build_worker(ApplyFixWorker, {
            "_iface": "eth0",
            "_algo": Algorithm.RED,
            "_parameters": {"min_th": 30, "max_th": 90, "max_p": 0.1, "limit": 128},
            "_score_before": 50.0,
            "_diagnostic_id": "diag-edge",
            "_latency_before_ms": None,
            "_loss_before_pct": None,
            "_controller": ctrl,
        })

        def fake_none_none(self_inner):
            return None, None

        with patch("sarichesko.core.traffic_control_manager.get_connection",
                    _shared_conn_factory(db_name)), \
             patch("sarichesko.core.traffic_control_manager.init_db"), \
             patch.object(ApplyFixWorker, "_run_verification", fake_none_none):
            worker.run()

        worker.complete.emit.assert_called_once()
        report = worker.complete.emit.call_args[0][0]
        assert report.applied is True
        assert report.score_after is None
        assert report.verdict is None
        assertion_conn.close()


# ===================================================================
# 5  RollbackWorker
# ===================================================================

class TestRollbackWorker:
    """Requirement 5: confirm rollback restores the snapshot and marks
    rolled_back_at in the database."""

    def test_rollback_restores_and_marks_timestamp(self):
        db_name = f"rb_{uuid.uuid4().hex[:8]}"
        assertion_conn = _make_shared_conn(db_name)
        repo = Repository(assertion_conn)

        # Pre-populate an applied policy row
        policy_id = str(uuid.uuid4())
        now = time.time()
        repo.save_applied_policy(AppliedPolicy(
            id=policy_id,
            diagnostic_id="diag-rb",
            timestamp=now,
            interface="wlan0",
            algorithm="Leaky Bucket",
            parameters=json.dumps({"rate_bps": 8_000_000, "burst_bytes": 32768}),
            snapshot_before="snapshot-data-before",
            score_before=55.0,
            score_after=35.0,
            verdict="improved",
        ))

        snapshot = ConfigSnapshot(interface="wlan0", raw="snapshot-data-before")
        ctrl = FakeController()

        worker = _build_worker(RollbackWorker, {
            "_policy_id": policy_id,
            "_snapshot": snapshot,
            "_controller": ctrl,
        })

        with patch("sarichesko.core.traffic_control_manager.get_connection",
                    _shared_conn_factory(db_name)), \
             patch("sarichesko.core.traffic_control_manager.init_db"):
            worker.run()

        # Controller was asked to restore
        assert ctrl._restored is True

        # DB row now has rolled_back_at set
        rows = repo.get_applied_policies(limit=10)
        row = next(r for r in rows if r["id"] == policy_id)
        assert row["rolled_back_at"] is not None
        assert row["rolled_back_at"] > 0

        # The emitted result is the ApplyResult from restore_snapshot
        worker.complete.emit.assert_called_once()
        result: ApplyResult = worker.complete.emit.call_args[0][0]
        assert result.success is True
        assertion_conn.close()

    def test_rollback_preserves_existing_fields(self):
        """Rollback must not clobber score_after or verdict when marking
        rolled_back_at."""
        db_name = f"rb2_{uuid.uuid4().hex[:8]}"
        assertion_conn = _make_shared_conn(db_name)
        repo = Repository(assertion_conn)

        policy_id = str(uuid.uuid4())
        repo.save_applied_policy(AppliedPolicy(
            id=policy_id,
            diagnostic_id="diag-rb2",
            timestamp=time.time(),
            interface="eth0",
            algorithm="Token Bucket",
            parameters="{}",
            snapshot_before="snap",
            score_before=60.0,
            score_after=40.0,
            verdict="improved",
        ))

        worker = _build_worker(RollbackWorker, {
            "_policy_id": policy_id,
            "_snapshot": ConfigSnapshot(interface="eth0", raw="snap"),
            "_controller": FakeController(),
        })

        with patch("sarichesko.core.traffic_control_manager.get_connection",
                    _shared_conn_factory(db_name)), \
             patch("sarichesko.core.traffic_control_manager.init_db"):
            worker.run()

        row = repo.get_applied_policies(limit=1)[0]
        assert row["score_after"] == 40.0
        assert row["verdict"] == "improved"
        assert row["rolled_back_at"] is not None
        assertion_conn.close()


# ===================================================================
# 6  Windows-specific safety guarantee
# ===================================================================

class TestWindowsSafetyGuarantee:
    """Requirement 6: apply_red() and apply_codel() on WindowsTrafficController
    must NEVER call subprocess.run at all — they must be pure refusals.
    Also test is_algorithm_supported() is side-effect-free."""

    def test_apply_red_never_calls_subprocess(self):
        from sarichesko.platform.windows.controller import WindowsTrafficController
        ctrl = WindowsTrafficController()
        with patch("sarichesko.platform.windows.controller.subprocess.run") as mock_run:
            result = ctrl.apply_red("Ethernet", min_th=30, max_th=90, max_p=0.1, limit=128)
            mock_run.assert_not_called()
        assert result.success is False

    def test_apply_codel_never_calls_subprocess(self):
        from sarichesko.platform.windows.controller import WindowsTrafficController
        ctrl = WindowsTrafficController()
        with patch("sarichesko.platform.windows.controller.subprocess.run") as mock_run:
            result = ctrl.apply_codel("Ethernet", target_ms=5, interval_ms=100, limit=1024)
            mock_run.assert_not_called()
        assert result.success is False

    def test_apply_red_message_explains_unavailable(self):
        from sarichesko.platform.windows.controller import WindowsTrafficController
        ctrl = WindowsTrafficController()
        with patch("sarichesko.platform.windows.controller.subprocess.run"):
            result = ctrl.apply_red("Ethernet", 30, 90, 0.1, 128)
        assert "unavailable" in result.message.lower() or "unsupported" in result.message.lower()

    def test_apply_codel_message_explains_unavailable(self):
        from sarichesko.platform.windows.controller import WindowsTrafficController
        ctrl = WindowsTrafficController()
        with patch("sarichesko.platform.windows.controller.subprocess.run"):
            result = ctrl.apply_codel("Ethernet", 5, 100, 1024)
        assert "unavailable" in result.message.lower() or "unsupported" in result.message.lower()

    def test_is_algorithm_supported_side_effect_free(self):
        """is_algorithm_supported() must never call subprocess."""
        from sarichesko.platform.windows.controller import WindowsTrafficController
        ctrl = WindowsTrafficController()
        with patch("sarichesko.platform.windows.controller.subprocess.run") as mock_run:
            assert ctrl.is_algorithm_supported("Leaky Bucket") is True
            assert ctrl.is_algorithm_supported("Token Bucket") is True
            assert ctrl.is_algorithm_supported("RED") is False
            assert ctrl.is_algorithm_supported("CoDel") is False
            mock_run.assert_not_called()

    def test_windows_supported_algorithms_set(self):
        from sarichesko.platform.windows.controller import WindowsTrafficController
        ctrl = WindowsTrafficController()
        assert "RED" not in ctrl.SUPPORTED_ALGORITHMS
        assert "CoDel" not in ctrl.SUPPORTED_ALGORITHMS
        assert "Leaky Bucket" in ctrl.SUPPORTED_ALGORITHMS
        assert "Token Bucket" in ctrl.SUPPORTED_ALGORITHMS


# ===================================================================
# 7  ABC enforcement — FINDING (not a test)
# ===================================================================
#
# TrafficControllerBase does NOT declare is_algorithm_supported() or
# unsupported_reason() as abstract methods. Neither method appears in
# base.py at all. They are concrete methods added independently on
# WindowsTrafficController and LinuxTrafficController.
#
# This means the ABC does NOT enforce that every subclass implements
# is_algorithm_supported(), which is a gap: a new controller subclass
# could silently omit it and crash at runtime instead of at class-
# definition time.
#
# FINDING: Consider adding is_algorithm_supported() as an @abstractmethod
# to TrafficControllerBase so the contract is enforced by the ABC.
# unsupported_reason() does not exist anywhere in the codebase.
#
# No test is written here because the methods are genuinely absent from
# the base class — the requirement says to note this as a finding.

class TestABCContractEnforcement:
    """Verify the abstract-method enforcement that IS in place on the
    base class, plus note the gap around is_algorithm_supported."""

    def test_base_class_cannot_be_instantiated(self):
        """TrafficControllerBase is a proper ABC — direct instantiation fails."""
        with pytest.raises(TypeError):
            TrafficControllerBase()

    def test_missing_abstract_method_fails(self):
        """A subclass missing any declared abstract method cannot be instantiated."""
        class IncompleteController(TrafficControllerBase):
            # Missing all abstract methods
            pass
        with pytest.raises(TypeError):
            IncompleteController()

    def test_is_algorithm_supported_not_abstract(self):
        """Documents the finding: is_algorithm_supported is not on the ABC."""
        import inspect
        abstract_methods = getattr(TrafficControllerBase, "__abstractmethods__", set())
        assert "is_algorithm_supported" not in abstract_methods, \
            "is_algorithm_supported is not currently abstract (this test documents that fact)"
