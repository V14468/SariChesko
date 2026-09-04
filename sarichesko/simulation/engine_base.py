from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AlgorithmType(Enum):
    NONE = "None"
    LEAKY_BUCKET = "Leaky Bucket"
    TOKEN_BUCKET = "Token Bucket"
    RED = "RED"
    CODEL = "CoDel"


@dataclass
class SimConfig:
    scenario: str
    algorithm: AlgorithmType
    duration_s: float = 10.0
    link_bandwidth_mbps: float = 10.0
    link_delay_ms: float = 20.0
    queue_size: int = 100
    num_flows: int = 5
    # Algorithm-specific params
    rate_bps: int = 5_000_000
    burst_bytes: int = 32768
    latency_ms: int = 50
    red_min_th: int = 20
    red_max_th: int = 60
    red_max_p: float = 0.1
    codel_target_ms: int = 5
    codel_interval_ms: int = 100


@dataclass
class PacketEvent:
    time: float
    event: str           # "arrive" | "depart" | "drop"
    packet_id: int
    queue_depth: int
    delay_ms: float


@dataclass
class SimMetrics:
    throughput_mbps: float = 0.0
    avg_latency_ms: float = 0.0
    max_latency_ms: float = 0.0
    loss_pct: float = 0.0
    avg_queue_depth: float = 0.0
    max_queue_depth: int = 0
    fairness_index: float = 0.0
    total_packets: int = 0
    dropped_packets: int = 0
    delivered_packets: int = 0


@dataclass
class SimulationResult:
    scenario: str
    algorithm: str
    config: SimConfig
    duration_s: float
    metrics: SimMetrics
    events: list[PacketEvent] = field(default_factory=list)
    queue_depth_over_time: list[tuple[float, int]] = field(default_factory=list)
    latency_over_time: list[tuple[float, float]] = field(default_factory=list)
    engine_used: str = "python_fallback"


class SimulationEngineBase(ABC):
    @abstractmethod
    def run(self, config: SimConfig) -> SimulationResult: ...