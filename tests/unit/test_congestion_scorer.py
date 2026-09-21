import pytest
from sarichesko.core.congestion_scorer import (
    classify_severity,
    score_congestion,
    CongestionScore,
    SEVERITY_THRESHOLDS,
)
from sarichesko.storage.models import Measurement, Baseline


def test_severity_thresholds_structure():
    assert len(SEVERITY_THRESHOLDS) == 5
    assert SEVERITY_THRESHOLDS[0] == (0, "NONE")
    assert SEVERITY_THRESHOLDS[4] == (85, "CRITICAL")


def test_classify_severity_none():
    assert classify_severity(0.0) == "NONE"
    assert classify_severity(10.0) == "NONE"
    assert classify_severity(19.9) == "NONE"


def test_classify_severity_mild():
    assert classify_severity(20.0) == "MILD"
    assert classify_severity(30.5) == "MILD"
    assert classify_severity(39.9) == "MILD"


def test_classify_severity_moderate():
    assert classify_severity(40.0) == "MODERATE"
    assert classify_severity(55.0) == "MODERATE"
    assert classify_severity(64.9) == "MODERATE"


def test_classify_severity_severe():
    assert classify_severity(65.0) == "SEVERE"
    assert classify_severity(75.0) == "SEVERE"
    assert classify_severity(84.9) == "SEVERE"


def test_classify_severity_critical():
    assert classify_severity(85.0) == "CRITICAL"
    assert classify_severity(99.0) == "CRITICAL"
    assert classify_severity(100.0) == "CRITICAL"


def test_score_congestion_none_baseline():
    curr = Measurement(session_id="s1", timestamp=100.0, latency_ms=50.0)
    result = score_congestion(curr, None)
    assert result.score == 0.0
    assert result.severity == "NONE"
    assert result.signals == {}
    assert result.dominant_signal == "none"
    assert not result.is_persistent
    assert result.trend == "STABLE"


def test_score_congestion_normal_conditions():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=20.0, latency_stddev_ms=2.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=1.0
    )
    curr = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=20.0, jitter_ms=1.0, packet_loss_pct=0.0,
        utilization_pct=30.0, queue_delay_ms=0.0
    )
    result = score_congestion(curr, base)
    assert result.score == 0.0
    assert result.severity == "NONE"


def test_score_congestion_lower_latency_than_baseline():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=50.0, latency_stddev_ms=5.0,
        loss_mean_pct=1.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=2.0
    )
    curr = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=30.0, jitter_ms=1.0, packet_loss_pct=0.0,
        utilization_pct=30.0, queue_delay_ms=0.0
    )
    result = score_congestion(curr, base)
    assert result.signals["latency_delta"] == 0.0
    assert result.signals["packet_loss"] == 0.0


def test_score_congestion_zero_mean_latency_in_baseline():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=0.0, latency_stddev_ms=1.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=1.0
    )
    curr = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=50.0, jitter_ms=1.0, packet_loss_pct=0.0,
        utilization_pct=30.0, queue_delay_ms=0.0
    )
    result = score_congestion(curr, base)
    assert result.signals["latency_delta"] == 0.0


def test_score_congestion_elevated_latency():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=20.0, latency_stddev_ms=2.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=1.0
    )
    curr = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=120.0, jitter_ms=1.0, packet_loss_pct=0.0,
        utilization_pct=30.0, queue_delay_ms=0.0
    )
    result = score_congestion(curr, base)
    assert result.score > 0.0
    assert result.signals["latency_delta"] > 50
    assert result.dominant_signal == "latency_delta"


def test_score_congestion_packet_loss():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=20.0, latency_stddev_ms=2.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=1.0
    )
    curr = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=20.0, jitter_ms=1.0, packet_loss_pct=5.0,
        utilization_pct=30.0, queue_delay_ms=0.0
    )
    result = score_congestion(curr, base)
    assert result.signals["packet_loss"] == 100.0
    assert result.dominant_signal == "packet_loss"
    assert result.score >= 30.0


def test_score_congestion_high_jitter():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=20.0, latency_stddev_ms=2.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=2.0
    )
    curr = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=20.0, jitter_ms=30.0, packet_loss_pct=0.0,
        utilization_pct=30.0, queue_delay_ms=0.0
    )
    result = score_congestion(curr, base)
    assert result.signals["jitter"] > 0
    assert result.signals["jitter"] == 100.0


def test_score_congestion_zero_baseline_jitter():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=20.0, latency_stddev_ms=2.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=0.0
    )
    curr = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=20.0, jitter_ms=10.0, packet_loss_pct=0.0,
        utilization_pct=30.0, queue_delay_ms=0.0
    )
    result = score_congestion(curr, base)
    assert result.signals["jitter"] == 50.0


def test_score_congestion_zero_baseline_jitter_small():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=20.0, latency_stddev_ms=2.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=0.0
    )
    curr = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=20.0, jitter_ms=1.5, packet_loss_pct=0.0,
        utilization_pct=30.0, queue_delay_ms=0.0
    )
    result = score_congestion(curr, base)
    assert result.signals["jitter"] == 0.0


def test_score_congestion_utilization():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=20.0, latency_stddev_ms=2.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=1.0
    )
    curr_low = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=20.0, jitter_ms=1.0, packet_loss_pct=0.0,
        utilization_pct=60.0, queue_delay_ms=0.0
    )
    assert score_congestion(curr_low, base).signals["utilization"] == 0.0

    curr_high = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=20.0, jitter_ms=1.0, packet_loss_pct=0.0,
        utilization_pct=90.0, queue_delay_ms=0.0
    )
    assert score_congestion(curr_high, base).signals["utilization"] == 60.0


def test_score_congestion_queue_delay():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=20.0, latency_stddev_ms=2.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=1.0
    )
    curr_low = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=20.0, jitter_ms=1.0, packet_loss_pct=0.0,
        utilization_pct=30.0, queue_delay_ms=4.0
    )
    assert score_congestion(curr_low, base).signals["queue_delay"] == 0.0

    curr_high = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=20.0, jitter_ms=1.0, packet_loss_pct=0.0,
        utilization_pct=30.0, queue_delay_ms=25.0
    )
    assert score_congestion(curr_high, base).signals["queue_delay"] == 50.0


def test_score_congestion_clamped_to_100():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=10.0, latency_stddev_ms=1.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=1.0
    )
    curr = Measurement(
        session_id="s1", timestamp=100.0,
        latency_ms=500.0, jitter_ms=100.0, packet_loss_pct=50.0,
        utilization_pct=110.0, queue_delay_ms=200.0
    )
    result = score_congestion(curr, base)
    assert result.score == 100.0
    assert result.severity == "CRITICAL"


def test_score_congestion_persistence():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=20.0, latency_stddev_ms=2.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=1.0
    )
    curr = Measurement(session_id="s1", timestamp=100.0, latency_ms=20.0)

    # 35 sustained scores > 30
    recent_persistent = [35.0] * 35
    assert score_congestion(curr, base, recent_persistent).is_persistent is True

    # Exactly 30 sustained scores > 30
    recent_exact_30 = [35.0] * 30
    assert score_congestion(curr, base, recent_exact_30).is_persistent is True

    # Less than 30 scores
    recent_short = [35.0] * 20
    assert score_congestion(curr, base, recent_short).is_persistent is False

    # 35 scores with one below 30 in the last 30
    recent_with_dip = [35.0] * 10 + [25.0] + [35.0] * 24
    assert score_congestion(curr, base, recent_with_dip).is_persistent is False


def test_score_congestion_trend():
    base = Baseline(
        interface="eth0", measured_at=10.0,
        latency_mean_ms=20.0, latency_stddev_ms=2.0,
        loss_mean_pct=0.0, bandwidth_mean_mbps=100.0, jitter_mean_ms=1.0
    )
    curr = Measurement(session_id="s1", timestamp=100.0, latency_ms=20.0)

    # Rising
    recent_rising = [10.0, 15.0, 20.0, 25.0, 30.0]
    assert score_congestion(curr, base, recent_rising).trend == "RISING"

    # Falling
    recent_falling = [50.0, 45.0, 40.0, 35.0, 30.0]
    assert score_congestion(curr, base, recent_falling).trend == "FALLING"

    # Stable
    recent_stable = [30.0, 32.0, 31.0, 30.0, 31.0]
    assert score_congestion(curr, base, recent_stable).trend == "STABLE"

    # Short history (< 5 items)
    recent_short = [10.0, 30.0]
    assert score_congestion(curr, base, recent_short).trend == "STABLE"
