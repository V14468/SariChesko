from dataclasses import dataclass
from enum import Enum
from typing import Optional

from .congestion_scorer import CongestionScore
from .isp_probe import ISPVerdict, ISPDiagnosticResult


class Algorithm(Enum):
    LEAKY_BUCKET = "Leaky Bucket"
    TOKEN_BUCKET = "Token Bucket"
    RED = "RED"
    CODEL = "CoDel"


@dataclass
class TrafficProfile:
    is_bursty: bool
    burst_tolerance: str          # "HIGH" | "LOW"
    needs_smooth_output: bool
    queue_growth_rate: float      # packets/sec estimate
    sojourn_time_ms: float        # avg time a packet sits in queue
    dominant_signal: str


@dataclass
class Recommendation:
    algo: Optional[Algorithm]
    parameters: dict
    reason: str
    confidence: str               # "HIGH" | "MEDIUM" | "LOW"
    actions: list[str]


QUEUE_GROWTH_THRESHOLD = 50.0
CODEL_TARGET_MS = 15.0


def build_traffic_profile(score: CongestionScore) -> TrafficProfile:
    signals = score.signals

    jitter_val = signals.get("jitter", 0)
    latency_val = signals.get("latency_delta", 0)
    loss_val = signals.get("packet_loss", 0)
    queue_val = signals.get("queue_delay", 0)

    is_bursty = jitter_val > 30
    burst_tolerance = "HIGH" if jitter_val < 60 else "LOW"
    needs_smooth = latency_val > 40 and jitter_val > 20
    queue_growth = loss_val * 2.5
    sojourn = queue_val * 0.8 + latency_val * 0.3

    return TrafficProfile(
        is_bursty=is_bursty,
        burst_tolerance=burst_tolerance,
        needs_smooth_output=needs_smooth,
        queue_growth_rate=queue_growth,
        sojourn_time_ms=sojourn,
        dominant_signal=score.dominant_signal,
    )


def recommend(
    score: CongestionScore,
    isp_result: Optional[ISPDiagnosticResult] = None,
) -> Recommendation:

    # If ISP issue — no local fix will help
    if isp_result and isp_result.verdict in (
        ISPVerdict.ISP_DEGRADATION, ISPVerdict.ISP_OUTAGE,
        ISPVerdict.LAST_MILE, ISPVerdict.DNS_ISSUE,
    ):
        verdict_names = {
            ISPVerdict.ISP_DEGRADATION: "ISP degradation (high latency to upstream hosts)",
            ISPVerdict.ISP_OUTAGE: "ISP upstream outage (WAN hosts unreachable)",
            ISPVerdict.LAST_MILE: "Last-mile issue (ISP first hop unreachable)",
            ISPVerdict.DNS_ISSUE: "DNS resolution failure",
        }
        return Recommendation(
            algo=None,
            parameters={},
            reason=f"Detected {verdict_names.get(isp_result.verdict, 'ISP-side issue')}. "
                   f"Local traffic shaping will not resolve this — the problem is upstream.",
            confidence="HIGH",
            actions=["Contact your ISP", "Check ISP status page", "Try alternative DNS (8.8.8.8 / 1.1.1.1)"],
        )

    # No congestion
    if score.score < 15:
        return Recommendation(
            algo=None,
            parameters={},
            reason="Network health is good — no congestion detected. No intervention needed.",
            confidence="HIGH",
            actions=["Continue monitoring"],
        )

    profile = build_traffic_profile(score)

    # Bursty traffic that tolerates bursts → Token Bucket
    if profile.is_bursty and profile.burst_tolerance == "HIGH":
        return Recommendation(
            algo=Algorithm.TOKEN_BUCKET,
            parameters={"rate_bps": 10_000_000, "burst_bytes": 65536, "latency_ms": 50},
            reason="Bursty traffic detected with acceptable burst tolerance. "
                   "Token Bucket will shape traffic while allowing legitimate bursts through, "
                   "smoothing peak load without starving bursty flows.",
            confidence="HIGH" if score.score > 40 else "MEDIUM",
            actions=["Apply Token Bucket shaping", "Monitor for 30s to verify improvement"],
        )

    # Needs smooth steady output → Leaky Bucket
    if profile.needs_smooth_output:
        return Recommendation(
            algo=Algorithm.LEAKY_BUCKET,
            parameters={"rate_bps": 8_000_000, "burst_bytes": 32768},
            reason="High jitter with elevated latency — traffic needs smoothing. "
                   "Leaky Bucket enforces a fixed output rate, converting bursty input "
                   "into a steady stream to reduce downstream queueing.",
            confidence="HIGH" if score.score > 40 else "MEDIUM",
            actions=["Apply Leaky Bucket shaping", "Monitor for 30s to verify improvement"],
        )

    # Rapidly growing queue → RED
    if profile.queue_growth_rate > QUEUE_GROWTH_THRESHOLD:
        return Recommendation(
            algo=Algorithm.RED,
            parameters={"min_th": 30, "max_th": 90, "max_p": 0.1, "limit": 128},
            reason="Packet loss indicates rapidly growing queues. "
                   "RED (Random Early Detection) probabilistically drops packets before "
                   "the queue is full, signalling TCP senders to back off early and "
                   "preventing tail-drop synchronization.",
            confidence="HIGH" if score.score > 50 else "MEDIUM",
            actions=["Apply RED active queue management", "Monitor for 30s to verify improvement"],
        )

    # Persistent queueing delay → CoDel
    if profile.sojourn_time_ms > CODEL_TARGET_MS:
        return Recommendation(
            algo=Algorithm.CODEL,
            parameters={"target_ms": 5, "interval_ms": 100, "limit": 1024},
            reason="Sustained queueing delay detected (bufferbloat pattern). "
                   "CoDel (Controlled Delay) targets excessive sojourn time rather than "
                   "queue length, dropping packets only when delay persists beyond the target, "
                   "which is more effective against bufferbloat than length-based approaches.",
            confidence="HIGH" if score.is_persistent else "MEDIUM",
            actions=["Apply CoDel queue management", "Monitor for 30s to verify improvement"],
        )

    # Fallback: moderate congestion, no clear pattern
    return Recommendation(
        algo=Algorithm.CODEL,
        parameters={"target_ms": 5, "interval_ms": 100, "limit": 1024},
        reason="Moderate congestion detected without a dominant pattern. "
               "CoDel is recommended as a general-purpose AQM that adapts well "
               "to varying traffic conditions by targeting delay rather than queue length.",
        confidence="LOW",
        actions=["Apply CoDel as a general remedy", "Run diagnostic again after 60s for a clearer signal"],
    )