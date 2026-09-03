from dataclasses import dataclass
from typing import Optional

from ..storage.models import Measurement, Baseline


@dataclass
class CongestionScore:
    score: float
    severity: str
    signals: dict
    dominant_signal: str
    is_persistent: bool
    trend: str


SEVERITY_THRESHOLDS = [
    (0, "NONE"),
    (20, "MILD"),
    (40, "MODERATE"),
    (65, "SEVERE"),
    (85, "CRITICAL"),
]


def classify_severity(score: float) -> str:
    result = "NONE"
    for threshold, label in SEVERITY_THRESHOLDS:
        if score >= threshold:
            result = label
    return result


def score_congestion(
    current: Measurement,
    baseline: Optional[Baseline],
    recent_scores: list[float] = None,
) -> CongestionScore:
    if baseline is None:
        return CongestionScore(
            score=0.0, severity="NONE", signals={},
            dominant_signal="none", is_persistent=False, trend="STABLE",
        )

    signals = {}

    # Latency delta
    if baseline.latency_mean_ms > 0 and baseline.latency_stddev_ms >= 0:
        delta = current.latency_ms - baseline.latency_mean_ms
        spread = baseline.latency_stddev_ms + 1.0
        signals["latency_delta"] = min(max((delta / spread) * 15, 0), 100)
    else:
        signals["latency_delta"] = 0.0

    # Packet loss
    excess_loss = current.packet_loss_pct - baseline.loss_mean_pct
    if excess_loss > 0:
        signals["packet_loss"] = min(excess_loss * 25, 100)
    else:
        signals["packet_loss"] = 0.0

    # Jitter
    if baseline.jitter_mean_ms > 0:
        jitter_ratio = current.jitter_ms / (baseline.jitter_mean_ms + 0.5)
        signals["jitter"] = min(max((jitter_ratio - 1.5) * 20, 0), 100)
    else:
        signals["jitter"] = min(current.jitter_ms * 5, 100) if current.jitter_ms > 2 else 0.0

    # Utilization
    signals["utilization"] = min(max((current.utilization_pct - 70) * 3, 0), 100)

    # Queue delay
    signals["queue_delay"] = min(current.queue_delay_ms * 2, 100) if current.queue_delay_ms > 5 else 0.0

    # Weighted composite
    weights = {
        "latency_delta": 0.25,
        "packet_loss": 0.30,
        "jitter": 0.15,
        "utilization": 0.20,
        "queue_delay": 0.10,
    }
    score = sum(signals.get(k, 0) * w for k, w in weights.items())
    score = round(min(score, 100), 1)

    # Dominant signal
    dominant = max(signals, key=signals.get) if signals else "none"

    # Persistence (sustained > 30 s worth of readings)
    is_persistent = False
    if recent_scores and len(recent_scores) >= 30:
        is_persistent = all(s > 30 for s in recent_scores[-30:])

    # Trend
    trend = "STABLE"
    if recent_scores and len(recent_scores) >= 5:
        recent = recent_scores[-5:]
        if recent[-1] > recent[0] + 10:
            trend = "RISING"
        elif recent[-1] < recent[0] - 10:
            trend = "FALLING"

    return CongestionScore(
        score=score,
        severity=classify_severity(score),
        signals=signals,
        dominant_signal=dominant,
        is_persistent=is_persistent,
        trend=trend,
    )