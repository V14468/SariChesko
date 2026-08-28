import time
import statistics
from typing import Optional

from PySide6.QtCore import QThread, Signal, QMutex

from ..platform import get_monitor
from ..platform.base import NetworkMonitorBase, InterfaceStats
from ..storage.models import Measurement, Baseline


class MonitorEngine(QThread):
    measurement_ready = Signal(object)
    congestion_alert = Signal(float, dict)
    baseline_established = Signal(object)
    error_occurred = Signal(str)

    def __init__(self, interface: str, session_id: str, interval_s: float = 1.0):
        super().__init__()
        self._iface = interface
        self._session_id = session_id
        self._interval = interval_s
        self._monitor: NetworkMonitorBase = get_monitor()
        self._running = False
        self._mutex = QMutex()

        self._prev_stats: Optional[InterfaceStats] = None
        self._prev_latency: Optional[float] = None
        self._history: list[Measurement] = []
        self._baseline: Optional[Baseline] = None
        self._baseline_window = 60

    @property
    def baseline(self) -> Optional[Baseline]:
        return self._baseline

    def set_baseline(self, b: Baseline) -> None:
        self._baseline = b

    def stop(self) -> None:
        self._mutex.lock()
        self._running = False
        self._mutex.unlock()

    def run(self) -> None:
        self._running = True
        self._prev_stats = self._monitor.get_stats(self._iface)
        time.sleep(self._interval)

        while True:
            self._mutex.lock()
            running = self._running
            self._mutex.unlock()
            if not running:
                break

            try:
                m = self._take_measurement()
                self._history.append(m)
                self.measurement_ready.emit(m)

                if self._baseline is None and len(self._history) >= self._baseline_window:
                    self._compute_baseline()

                if self._baseline is not None:
                    score, signals = self._check_anomaly(m)
                    if score > 30:
                        self.congestion_alert.emit(score, signals)

            except Exception as e:
                self.error_occurred.emit(str(e))

            time.sleep(self._interval)

    def _take_measurement(self) -> Measurement:
        now = time.time()
        cur = self._monitor.get_stats(self._iface)
        dt = cur.timestamp - self._prev_stats.timestamp
        if dt <= 0:
            dt = self._interval

        bytes_in = cur.bytes_recv - self._prev_stats.bytes_recv
        bytes_out = cur.bytes_sent - self._prev_stats.bytes_sent
        bandwidth_mbps = ((bytes_in + bytes_out) * 8) / (dt * 1_000_000)

        packets_total = (cur.packets_recv - self._prev_stats.packets_recv) + \
                        (cur.packets_sent - self._prev_stats.packets_sent)
        drops = (cur.dropin - self._prev_stats.dropin) + (cur.dropout - self._prev_stats.dropout)
        loss_pct = (drops / packets_total * 100) if packets_total > 0 else 0.0

        ping_result = self._monitor.ping("8.8.8.8", count=1)
        latency_ms = ping_result.latency_ms or 0.0

        jitter_ms = abs(latency_ms - self._prev_latency) if self._prev_latency is not None else 0.0
        self._prev_latency = latency_ms

        self._prev_stats = cur

        return Measurement(
            session_id=self._session_id,
            timestamp=now,
            bandwidth_mbps=round(bandwidth_mbps, 3),
            latency_ms=round(latency_ms, 2),
            jitter_ms=round(jitter_ms, 2),
            packet_loss_pct=round(loss_pct, 4),
            utilization_pct=0.0,
            queue_delay_ms=0.0,
        )

    def _compute_baseline(self) -> None:
        window = self._history[-self._baseline_window:]
        lats = [m.latency_ms for m in window if m.latency_ms > 0]
        losses = [m.packet_loss_pct for m in window]
        bws = [m.bandwidth_mbps for m in window]
        jits = [m.jitter_ms for m in window]

        self._baseline = Baseline(
            interface=self._iface,
            measured_at=time.time(),
            latency_mean_ms=statistics.mean(lats) if lats else 0.0,
            latency_stddev_ms=statistics.stdev(lats) if len(lats) > 1 else 0.0,
            loss_mean_pct=statistics.mean(losses) if losses else 0.0,
            bandwidth_mean_mbps=statistics.mean(bws) if bws else 0.0,
            jitter_mean_ms=statistics.mean(jits) if jits else 0.0,
        )
        self.baseline_established.emit(self._baseline)

    def _check_anomaly(self, m: Measurement) -> tuple[float, dict]:
        b = self._baseline
        signals = {}

        lat_threshold = b.latency_mean_ms + 2 * b.latency_stddev_ms
        if lat_threshold > 0 and m.latency_ms > lat_threshold:
            signals["latency"] = min((m.latency_ms - b.latency_mean_ms) / (b.latency_stddev_ms + 0.01) * 10, 100)
        else:
            signals["latency"] = 0.0

        if m.packet_loss_pct > b.loss_mean_pct + 1.0:
            signals["packet_loss"] = min(m.packet_loss_pct * 20, 100)
        else:
            signals["packet_loss"] = 0.0

        if m.jitter_ms > b.jitter_mean_ms * 3 + 5:
            signals["jitter"] = min(m.jitter_ms / (b.jitter_mean_ms + 1) * 15, 100)
        else:
            signals["jitter"] = 0.0

        score = (
            signals.get("latency", 0) * 0.4 +
            signals.get("packet_loss", 0) * 0.4 +
            signals.get("jitter", 0) * 0.2
        )
        return round(score, 1), signals