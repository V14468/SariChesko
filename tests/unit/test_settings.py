"""Tests for the congestion_sensitivity parameter in classify_severity()
and score_congestion(), and for is_elevated() fail-safety.

These are additive — they must not break any existing test_congestion_scorer.py
assertions. The default sensitivity=1.0 must reproduce exact existing behavior.
"""
import pytest
from sarichesko.core.congestion_scorer import classify_severity, score_congestion
from sarichesko.storage.models import Measurement, Baseline


# ===================================================================
# 1  classify_severity() with sensitivity
# ===================================================================

class TestClassifySeverityDefault:
    """Default sensitivity=1.0 must reproduce every existing boundary."""

    def test_none_boundary(self):
        assert classify_severity(0.0) == "NONE"
        assert classify_severity(19.9) == "NONE"

    def test_mild_boundary(self):
        assert classify_severity(20.0) == "MILD"
        assert classify_severity(39.9) == "MILD"

    def test_moderate_boundary(self):
        assert classify_severity(40.0) == "MODERATE"
        assert classify_severity(64.9) == "MODERATE"

    def test_severe_boundary(self):
        assert classify_severity(65.0) == "SEVERE"
        assert classify_severity(84.9) == "SEVERE"

    def test_critical_boundary(self):
        assert classify_severity(85.0) == "CRITICAL"
        assert classify_severity(100.0) == "CRITICAL"


class TestClassifySeverityHighSensitivity:
    """sensitivity > 1.0 lowers effective thresholds, flagging congestion
    sooner (at lower raw scores)."""

    def test_mild_reached_sooner(self):
        # threshold 20 / 1.5 = 13.33...
        assert classify_severity(14.0, sensitivity=1.5) == "MILD"
        assert classify_severity(13.0, sensitivity=1.5) == "NONE"

    def test_moderate_reached_sooner(self):
        # threshold 40 / 1.5 = 26.67
        assert classify_severity(27.0, sensitivity=1.5) == "MODERATE"
        assert classify_severity(26.0, sensitivity=1.5) == "MILD"

    def test_severe_reached_sooner(self):
        # threshold 65 / 1.5 = 43.33
        assert classify_severity(44.0, sensitivity=1.5) == "SEVERE"
        assert classify_severity(43.0, sensitivity=1.5) == "MODERATE"

    def test_critical_reached_sooner(self):
        # threshold 85 / 1.5 = 56.67
        assert classify_severity(57.0, sensitivity=1.5) == "CRITICAL"
        assert classify_severity(56.0, sensitivity=1.5) == "SEVERE"


class TestClassifySeverityLowSensitivity:
    """sensitivity < 1.0 raises effective thresholds, requiring more evidence
    before flagging congestion."""

    def test_mild_requires_more(self):
        # threshold 20 / 0.75 = 26.67
        assert classify_severity(25.0, sensitivity=0.75) == "NONE"
        assert classify_severity(27.0, sensitivity=0.75) == "MILD"

    def test_moderate_requires_more(self):
        # threshold 40 / 0.75 = 53.33
        assert classify_severity(53.0, sensitivity=0.75) == "MILD"
        assert classify_severity(54.0, sensitivity=0.75) == "MODERATE"

    def test_critical_requires_more(self):
        # threshold 85 / 0.75 = 113.33
        assert classify_severity(100.0, sensitivity=0.75) == "SEVERE"


class TestScoreCongestionSensitivity:
    """score_congestion() passes sensitivity through to classify_severity,
    which changes the severity label of the returned CongestionScore."""

    _BASE = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=20.0, latency_stddev_ms=2.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=1.0,
    )

    def _m(self, loss=0.0, latency=20.0, jitter=1.0, util=30.0, qd=0.0):
        return Measurement(
            session_id="s1", timestamp=100.0,
            latency_ms=latency, jitter_ms=jitter, packet_loss_pct=loss,
            utilization_pct=util, queue_delay_ms=qd,
        )

    def test_default_same_as_explicit_1_0(self):
        m = self._m(loss=2.0, latency=50.0, jitter=5.0, util=80.0)
        r_default = score_congestion(m, self._BASE)
        r_explicit = score_congestion(m, self._BASE, sensitivity=1.0)
        assert r_default.score == r_explicit.score
        assert r_default.severity == r_explicit.severity

    def test_high_sensitivity_escalates_severity(self):
        m = self._m(loss=2.0, latency=50.0, jitter=5.0, util=80.0, qd=10.0)
        r_balanced = score_congestion(m, self._BASE, sensitivity=1.0)
        r_aggressive = score_congestion(m, self._BASE, sensitivity=1.5)
        # Score is the same (sensitivity doesn't change signal calculation)
        assert r_balanced.score == r_aggressive.score
        # But severity should be at least as severe
        severity_order = ["NONE", "MILD", "MODERATE", "SEVERE", "CRITICAL"]
        assert severity_order.index(r_aggressive.severity) >= severity_order.index(r_balanced.severity)

    def test_low_sensitivity_deescalates_severity(self):
        m = self._m(loss=2.0, latency=50.0, jitter=5.0, util=80.0, qd=10.0)
        r_balanced = score_congestion(m, self._BASE, sensitivity=1.0)
        r_conservative = score_congestion(m, self._BASE, sensitivity=0.75)
        severity_order = ["NONE", "MILD", "MODERATE", "SEVERE", "CRITICAL"]
        assert severity_order.index(r_conservative.severity) <= severity_order.index(r_balanced.severity)


# ===================================================================
# 2  is_elevated() fail-safety on non-native platform
# ===================================================================

class TestIsElevatedFailSafe:
    """WindowsTrafficController.is_elevated() must return False (never
    raise) when called outside a real Windows environment."""

    def test_returns_false_no_crash(self):
        from sarichesko.platform.windows.controller import WindowsTrafficController
        ctrl = WindowsTrafficController()
        result = ctrl.is_elevated()
        assert isinstance(result, bool)
        # On a non-elevated process, or on Linux, this should be False.
        # On an elevated Windows process it could be True — that's also fine.
        # The key invariant: it must NOT raise.
