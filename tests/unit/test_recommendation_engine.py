import pytest
from sarichesko.core.congestion_scorer import CongestionScore
from sarichesko.core.isp_probe import ISPVerdict, ISPDiagnosticResult
from sarichesko.core.recommendation_engine import (
    Algorithm,
    TrafficProfile,
    Recommendation,
    build_traffic_profile,
    recommend,
    QUEUE_GROWTH_THRESHOLD,
    CODEL_TARGET_MS,
)


def test_algorithm_enum():
    assert Algorithm.LEAKY_BUCKET.value == "Leaky Bucket"
    assert Algorithm.TOKEN_BUCKET.value == "Token Bucket"
    assert Algorithm.RED.value == "RED"
    assert Algorithm.CODEL.value == "CoDel"


def test_traffic_profile_dataclass():
    tp = TrafficProfile(
        is_bursty=True,
        burst_tolerance="HIGH",
        needs_smooth_output=False,
        queue_growth_rate=12.5,
        sojourn_time_ms=8.0,
        dominant_signal="jitter",
    )
    assert tp.is_bursty is True
    assert tp.burst_tolerance == "HIGH"
    assert tp.dominant_signal == "jitter"


def test_recommendation_dataclass():
    rec = Recommendation(
        algo=Algorithm.TOKEN_BUCKET,
        parameters={"rate_bps": 1000},
        reason="Test reason",
        confidence="HIGH",
        actions=["Action 1", "Action 2"],
    )
    assert rec.algo == Algorithm.TOKEN_BUCKET
    assert rec.confidence == "HIGH"
    assert len(rec.actions) == 2


def test_build_traffic_profile_bursty():
    score = CongestionScore(
        score=50.0, severity="MODERATE",
        signals={"jitter": 40.0, "latency_delta": 10.0, "packet_loss": 5.0, "queue_delay": 10.0},
        dominant_signal="jitter", is_persistent=False, trend="STABLE"
    )
    profile = build_traffic_profile(score)
    assert profile.is_bursty is True
    assert profile.burst_tolerance == "HIGH"
    assert profile.needs_smooth_output is False
    assert profile.queue_growth_rate == 5.0 * 2.5
    assert profile.sojourn_time_ms == (10.0 * 0.8) + (10.0 * 0.3)


def test_build_traffic_profile_low_tolerance():
    score = CongestionScore(
        score=70.0, severity="SEVERE",
        signals={"jitter": 70.0, "latency_delta": 50.0, "packet_loss": 0.0, "queue_delay": 0.0},
        dominant_signal="jitter", is_persistent=False, trend="STABLE"
    )
    profile = build_traffic_profile(score)
    assert profile.is_bursty is True
    assert profile.burst_tolerance == "LOW"
    assert profile.needs_smooth_output is True


def test_recommend_isp_issues():
    score = CongestionScore(
        score=75.0, severity="SEVERE", signals={}, dominant_signal="none",
        is_persistent=False, trend="STABLE"
    )

    for verdict in (ISPVerdict.ISP_DEGRADATION, ISPVerdict.ISP_OUTAGE, ISPVerdict.LAST_MILE, ISPVerdict.DNS_ISSUE):
        isp_res = ISPDiagnosticResult(
            timestamp=100.0, verdict=verdict, gateway_latency_ms=1.0,
            isp_hop_latency_ms=None, wan_latency_ms=None, dns_ok=False,
            details="ISP issue", probe_results=[]
        )
        rec = recommend(score, isp_res)
        assert rec.algo is None
        assert rec.confidence == "HIGH"
        assert "upstream" in rec.reason.lower() or "dns" in rec.reason.lower()
        assert len(rec.actions) > 0


def test_recommend_healthy_network():
    score = CongestionScore(
        score=10.0, severity="NONE", signals={}, dominant_signal="none",
        is_persistent=False, trend="STABLE"
    )
    rec = recommend(score)
    assert rec.algo is None
    assert "no congestion detected" in rec.reason
    assert rec.confidence == "HIGH"


def test_recommend_token_bucket():
    score = CongestionScore(
        score=45.0, severity="MODERATE",
        signals={"jitter": 40.0, "latency_delta": 10.0, "packet_loss": 0.0, "queue_delay": 0.0},
        dominant_signal="jitter", is_persistent=False, trend="STABLE"
    )
    rec = recommend(score)
    assert rec.algo == Algorithm.TOKEN_BUCKET
    assert "Token Bucket" in rec.reason
    assert rec.confidence == "HIGH"
    assert "rate_bps" in rec.parameters
    assert "burst_bytes" in rec.parameters


def test_recommend_token_bucket_medium_confidence():
    score = CongestionScore(
        score=30.0, severity="MILD",
        signals={"jitter": 40.0, "latency_delta": 10.0, "packet_loss": 0.0, "queue_delay": 0.0},
        dominant_signal="jitter", is_persistent=False, trend="STABLE"
    )
    rec = recommend(score)
    assert rec.algo == Algorithm.TOKEN_BUCKET
    assert rec.confidence == "MEDIUM"


def test_recommend_leaky_bucket():
    score = CongestionScore(
        score=55.0, severity="MODERATE",
        signals={"jitter": 70.0, "latency_delta": 50.0, "packet_loss": 0.0, "queue_delay": 0.0},
        dominant_signal="jitter", is_persistent=False, trend="STABLE"
    )
    rec = recommend(score)
    assert rec.algo == Algorithm.LEAKY_BUCKET
    assert "Leaky Bucket" in rec.reason
    assert rec.confidence == "HIGH"
    assert "rate_bps" in rec.parameters


def test_recommend_red():
    score = CongestionScore(
        score=60.0, severity="MODERATE",
        # packet_loss > 20 -> queue_growth_rate = loss * 2.5 > 50
        signals={"jitter": 10.0, "latency_delta": 10.0, "packet_loss": 30.0, "queue_delay": 5.0},
        dominant_signal="packet_loss", is_persistent=False, trend="STABLE"
    )
    rec = recommend(score)
    assert rec.algo == Algorithm.RED
    assert "RED" in rec.reason
    assert rec.confidence == "HIGH"
    assert "min_th" in rec.parameters
    assert "max_th" in rec.parameters


def test_recommend_red_medium_confidence():
    score = CongestionScore(
        score=45.0, severity="MODERATE",
        signals={"jitter": 10.0, "latency_delta": 10.0, "packet_loss": 25.0, "queue_delay": 5.0},
        dominant_signal="packet_loss", is_persistent=False, trend="STABLE"
    )
    rec = recommend(score)
    assert rec.algo == Algorithm.RED
    assert rec.confidence == "MEDIUM"


def test_recommend_codel_sojourn_delay():
    score = CongestionScore(
        score=50.0, severity="MODERATE",
        # sojourn = queue_delay * 0.8 + latency_delta * 0.3 > 15
        signals={"jitter": 10.0, "latency_delta": 10.0, "packet_loss": 0.0, "queue_delay": 25.0},
        dominant_signal="queue_delay", is_persistent=True, trend="STABLE"
    )
    rec = recommend(score)
    assert rec.algo == Algorithm.CODEL
    assert "CoDel" in rec.reason
    assert rec.confidence == "HIGH"
    assert "target_ms" in rec.parameters
    assert "interval_ms" in rec.parameters


def test_recommend_codel_non_persistent_medium_confidence():
    score = CongestionScore(
        score=50.0, severity="MODERATE",
        signals={"jitter": 10.0, "latency_delta": 10.0, "packet_loss": 0.0, "queue_delay": 25.0},
        dominant_signal="queue_delay", is_persistent=False, trend="STABLE"
    )
    rec = recommend(score)
    assert rec.algo == Algorithm.CODEL
    assert rec.confidence == "MEDIUM"


def test_recommend_codel_fallback():
    score = CongestionScore(
        score=25.0, severity="MILD",
        # sojourn <= 15, jitter <= 30, queue_growth <= 50
        signals={"jitter": 10.0, "latency_delta": 10.0, "packet_loss": 0.0, "queue_delay": 5.0},
        dominant_signal="none", is_persistent=False, trend="STABLE"
    )
    rec = recommend(score)
    assert rec.algo == Algorithm.CODEL
    assert rec.confidence == "LOW"
    assert "Moderate congestion detected without a dominant pattern" in rec.reason
