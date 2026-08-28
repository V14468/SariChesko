from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class InterfaceInfo:
    name: str
    display_name: str
    is_up: bool
    speed_mbps: Optional[float]
    mac: str


@dataclass
class InterfaceStats:
    timestamp: float
    iface: str
    bytes_sent: int
    bytes_recv: int
    packets_sent: int
    packets_recv: int
    errin: int
    errout: int
    dropin: int
    dropout: int


@dataclass
class PingResult:
    host: str
    success: bool
    latency_ms: Optional[float]
    error: Optional[str] = None


@dataclass
class TracerouteHop:
    hop: int
    host: str
    latency_ms: Optional[float]


@dataclass
class ConfigSnapshot:
    interface: str
    raw: str


@dataclass
class ApplyResult:
    success: bool
    message: str


class NetworkMonitorBase(ABC):
    @abstractmethod
    def get_interfaces(self) -> list[InterfaceInfo]: ...

    @abstractmethod
    def get_stats(self, iface: str) -> InterfaceStats: ...

    @abstractmethod
    def ping(self, host: str, count: int = 4) -> PingResult: ...

    @abstractmethod
    def traceroute(self, host: str, max_hops: int = 5) -> list[TracerouteHop]: ...

    @abstractmethod
    def get_default_gateway(self) -> Optional[str]: ...

    @abstractmethod
    def get_dns_servers(self) -> list[str]: ...


class TrafficControllerBase(ABC):
    @abstractmethod
    def is_supported(self) -> bool: ...

    @abstractmethod
    def requires_elevation(self) -> bool: ...

    @abstractmethod
    def save_snapshot(self, iface: str) -> ConfigSnapshot: ...

    @abstractmethod
    def restore_snapshot(self, snapshot: ConfigSnapshot) -> ApplyResult: ...

    @abstractmethod
    def apply_leaky_bucket(self, iface: str, rate_bps: int, burst_bytes: int) -> ApplyResult: ...

    @abstractmethod
    def apply_token_bucket(self, iface: str, rate_bps: int, burst_bytes: int, latency_ms: int) -> ApplyResult: ...

    @abstractmethod
    def apply_red(self, iface: str, min_th: int, max_th: int, max_p: float, limit: int) -> ApplyResult: ...

    @abstractmethod
    def apply_codel(self, iface: str, target_ms: int, interval_ms: int, limit: int) -> ApplyResult: ...

    @abstractmethod
    def remove_policy(self, iface: str) -> ApplyResult: ...