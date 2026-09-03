import time
import uuid
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QThread, Signal

from .isp_probe import ISPDiagnosticResult, ISPProbeWorker
from .congestion_scorer import score_congestion, CongestionScore
from .recommendation_engine import recommend, Recommendation, TrafficProfile, build_traffic_profile
from ..platform import get_monitor
from ..storage.models import Measurement, Baseline, DiagnosticRun, ISPDiagnostic, Session
from ..storage.db import get_connection, init_db
from ..storage.repository import Repository


@dataclass
class DiagnosticResult:
    id: str
    timestamp: float
    congestion_score: CongestionScore
    isp_result: ISPDiagnosticResult
    traffic_profile: TrafficProfile
    recommendation: Recommendation
    measurements: list[Measurement]


class DiagnosticsWorker(QThread):
    progress = Signal(str, int)
    complete = Signal(object)
    error = Signal(str)

    def __init__(self, interface: str, session_id: Optional[str] = None):
        super().__init__()
        self._iface = interface
        self._session_id = session_id or str(uuid.uuid4())
        self._monitor = get_monitor()

    def run(self):
        conn = None
        try:
            conn = get_connection()
            conn.execute("PRAGMA busy_timeout = 5000")
            init_db(conn)
            repo = Repository(conn)

            diag_id = str(uuid.uuid4())
            now = time.time()

            # Create session row first so foreign keys work
            repo.save_session(Session(
                id=self._session_id,
                started_at=now,
                mode="diagnostic",
                interface=self._iface,
            ))

            # Step 1: ISP Probe
            self.progress.emit("Running ISP diagnostics...", 10)
            probe = ISPProbeWorker()
            isp_result = probe._run_probes()
            self.progress.emit("ISP probe complete", 35)

            # Step 2: Take measurements
            self.progress.emit("Measuring network conditions...", 40)
            measurements = []
            prev_stats = self._monitor.get_stats(self._iface)
            prev_latency = None

            for i in range(10):
                time.sleep(0.5)
                self.progress.emit(f"Collecting sample {i+1}/10...", 40 + i * 4)

                cur_stats = self._monitor.get_stats(self._iface)
                dt = cur_stats.timestamp - prev_stats.timestamp
                if dt <= 0:
                    dt = 0.5

                bytes_total = (cur_stats.bytes_recv - prev_stats.bytes_recv) + \
                              (cur_stats.bytes_sent - prev_stats.bytes_sent)
                bw = (bytes_total * 8) / (dt * 1_000_000)

                packets_total = (cur_stats.packets_recv - prev_stats.packets_recv) + \
                                (cur_stats.packets_sent - prev_stats.packets_sent)
                drops = (cur_stats.dropin - prev_stats.dropin) + (cur_stats.dropout - prev_stats.dropout)
                loss = (drops / packets_total * 100) if packets_total > 0 else 0.0

                ping_result = self._monitor.ping("8.8.8.8", count=1)
                latency = ping_result.latency_ms or 0.0
                jitter = abs(latency - prev_latency) if prev_latency is not None else 0.0
                prev_latency = latency

                m = Measurement(
                    session_id=self._session_id,
                    timestamp=time.time(),
                    bandwidth_mbps=round(bw, 3),
                    latency_ms=round(latency, 2),
                    jitter_ms=round(jitter, 2),
                    packet_loss_pct=round(loss, 4),
                    utilization_pct=0.0,
                    queue_delay_ms=0.0,
                )
                measurements.append(m)
                repo.save_measurement(m)
                prev_stats = cur_stats

            self.progress.emit("Scoring congestion...", 85)

            # Step 3: Score using averaged measurement
            avg_m = Measurement(
                session_id=self._session_id,
                timestamp=now,
                bandwidth_mbps=sum(m.bandwidth_mbps for m in measurements) / len(measurements),
                latency_ms=sum(m.latency_ms for m in measurements) / len(measurements),
                jitter_ms=sum(m.jitter_ms for m in measurements) / len(measurements),
                packet_loss_pct=sum(m.packet_loss_pct for m in measurements) / len(measurements),
                utilization_pct=0.0,
                queue_delay_ms=0.0,
            )

            baseline = repo.get_baseline(self._iface)
            cong_score = score_congestion(avg_m, baseline)

            # Step 4: Build traffic profile and recommend
            self.progress.emit("Generating recommendation...", 92)
            profile = build_traffic_profile(cong_score)
            rec = recommend(cong_score, isp_result)

            # Step 5: Persist
            self.progress.emit("Saving results...", 97)

            repo.save_isp_diagnostic(ISPDiagnostic(
                session_id=self._session_id,
                timestamp=now,
                verdict=isp_result.verdict.value,
                details=isp_result.details,
                gateway_ms=isp_result.gateway_latency_ms,
                isp_hop_ms=isp_result.isp_hop_latency_ms,
                wan_ms=isp_result.wan_latency_ms,
                dns_ok=isp_result.dns_ok,
            ))

            repo.save_diagnostic_run(DiagnosticRun(
                id=diag_id,
                session_id=self._session_id,
                timestamp=now,
                congestion_score=cong_score.score,
                severity=cong_score.severity,
                dominant_signal=cong_score.dominant_signal,
                isp_verdict=isp_result.verdict.value,
                recommended_algo=rec.algo.value if rec.algo else None,
                recommendation_reason=rec.reason,
                confidence=rec.confidence,
            ))

            # End session
            repo.end_session(self._session_id, time.time())

            result = DiagnosticResult(
                id=diag_id,
                timestamp=now,
                congestion_score=cong_score,
                isp_result=isp_result,
                traffic_profile=profile,
                recommendation=rec,
                measurements=measurements,
            )

            self.progress.emit("Complete!", 100)
            self.complete.emit(result)

        except Exception as e:
            self.error.emit(str(e))
        finally:
            if conn:
                conn.close()