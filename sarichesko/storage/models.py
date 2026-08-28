from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Session:
    id: str
    started_at: float
    mode: str = "real"
    ended_at: Optional[float] = None
    interface: Optional[str] = None


@dataclass
class Measurement:
    session_id: str
    timestamp: float
    bandwidth_mbps: float = 0.0
    latency_ms: float = 0.0
    jitter_ms: float = 0.0
    packet_loss_pct: float = 0.0
    utilization_pct: float = 0.0
    queue_delay_ms: float = 0.0
    id: Optional[int] = None


@dataclass
class Baseline:
    interface: str
    measured_at: float
    latency_mean_ms: float = 0.0
    latency_stddev_ms: float = 0.0
    loss_mean_pct: float = 0.0
    bandwidth_mean_mbps: float = 0.0
    jitter_mean_ms: float = 0.0


@dataclass
class ISPDiagnostic:
    session_id: str
    timestamp: float
    verdict: str
    details: str
    gateway_ms: Optional[float] = None
    isp_hop_ms: Optional[float] = None
    wan_ms: Optional[float] = None
    dns_ok: bool = False
    id: Optional[int] = None


@dataclass
class DiagnosticRun:
    id: str
    session_id: str
    timestamp: float
    congestion_score: float
    severity: str
    dominant_signal: str
    isp_verdict: str
    recommended_algo: Optional[str] = None
    recommendation_reason: Optional[str] = None
    confidence: Optional[str] = None


@dataclass
class AppliedPolicy:
    id: str
    timestamp: float
    interface: str
    algorithm: str
    parameters: str
    snapshot_before: str
    score_before: float
    diagnostic_id: Optional[str] = None
    score_after: Optional[float] = None
    verdict: Optional[str] = None
    rolled_back_at: Optional[float] = None


@dataclass
class SimulationResult:
    id: str
    timestamp: float
    scenario: str
    algorithm: str
    engine_used: str
    parameters: str = "{}"
    throughput_mbps: float = 0.0
    avg_latency_ms: float = 0.0
    loss_pct: float = 0.0
    fairness_index: float = 0.0
    metrics_detail: str = "{}"