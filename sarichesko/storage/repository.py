import sqlite3
import json
from typing import Optional
from .models import Session, Measurement, Baseline, ISPDiagnostic, DiagnosticRun, AppliedPolicy, SimulationResult


class Repository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    # --- Sessions ---
    def save_session(self, s: Session) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO sessions (id, started_at, ended_at, interface, mode) VALUES (?,?,?,?,?)",
            (s.id, s.started_at, s.ended_at, s.interface, s.mode)
        )
        self._conn.commit()

    def end_session(self, session_id: str, ended_at: float) -> None:
        self._conn.execute("UPDATE sessions SET ended_at=? WHERE id=?", (ended_at, session_id))
        self._conn.commit()

    # --- Measurements ---
    def save_measurement(self, m: Measurement) -> None:
        self._conn.execute(
            """INSERT INTO measurements
               (session_id, timestamp, bandwidth_mbps, latency_ms, jitter_ms,
                packet_loss_pct, utilization_pct, queue_delay_ms)
               VALUES (?,?,?,?,?,?,?,?)""",
            (m.session_id, m.timestamp, m.bandwidth_mbps, m.latency_ms,
             m.jitter_ms, m.packet_loss_pct, m.utilization_pct, m.queue_delay_ms)
        )
        self._conn.commit()

    def get_recent_measurements(self, session_id: str, limit: int = 300) -> list:
        rows = self._conn.execute(
            "SELECT * FROM measurements WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Baselines ---
    def save_baseline(self, b: Baseline) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO baselines
               (interface, measured_at, latency_mean_ms, latency_stddev_ms,
                loss_mean_pct, bandwidth_mean_mbps, jitter_mean_ms)
               VALUES (?,?,?,?,?,?,?)""",
            (b.interface, b.measured_at, b.latency_mean_ms, b.latency_stddev_ms,
             b.loss_mean_pct, b.bandwidth_mean_mbps, b.jitter_mean_ms)
        )
        self._conn.commit()

    def get_baseline(self, interface: str) -> Optional[Baseline]:
        row = self._conn.execute(
            "SELECT * FROM baselines WHERE interface=?", (interface,)
        ).fetchone()
        if not row:
            return None
        r = dict(row)
        return Baseline(**r)

    # --- ISP Diagnostics ---
    def save_isp_diagnostic(self, d: ISPDiagnostic) -> None:
        self._conn.execute(
            """INSERT INTO isp_diagnostics
               (session_id, timestamp, verdict, gateway_ms, isp_hop_ms, wan_ms, dns_ok, details)
               VALUES (?,?,?,?,?,?,?,?)""",
            (d.session_id, d.timestamp, d.verdict, d.gateway_ms,
             d.isp_hop_ms, d.wan_ms, int(d.dns_ok), d.details)
        )
        self._conn.commit()

    # --- Diagnostic Runs ---
    def save_diagnostic_run(self, r: DiagnosticRun) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO diagnostic_runs
               (id, session_id, timestamp, congestion_score, severity, dominant_signal,
                isp_verdict, recommended_algo, recommendation_reason, confidence)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (r.id, r.session_id, r.timestamp, r.congestion_score, r.severity,
             r.dominant_signal, r.isp_verdict, r.recommended_algo,
             r.recommendation_reason, r.confidence)
        )
        self._conn.commit()

    def get_diagnostic_runs(self, limit: int = 50) -> list:
        rows = self._conn.execute(
            "SELECT * FROM diagnostic_runs ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Applied Policies ---
    def save_applied_policy(self, p: AppliedPolicy) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO applied_policies
               (id, diagnostic_id, timestamp, interface, algorithm, parameters,
                snapshot_before, score_before, score_after, verdict, rolled_back_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (p.id, p.diagnostic_id, p.timestamp, p.interface, p.algorithm,
             p.parameters, p.snapshot_before, p.score_before, p.score_after,
             p.verdict, p.rolled_back_at)
        )
        self._conn.commit()

    # --- Simulation Results ---
    def save_simulation_result(self, r: SimulationResult) -> None:
        self._conn.execute(
            """INSERT OR REPLACE INTO simulation_results
               (id, timestamp, scenario, algorithm, parameters, engine_used,
                throughput_mbps, avg_latency_ms, loss_pct, fairness_index, metrics_detail)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (r.id, r.timestamp, r.scenario, r.algorithm, r.parameters,
             r.engine_used, r.throughput_mbps, r.avg_latency_ms,
             r.loss_pct, r.fairness_index, r.metrics_detail)
        )
        self._conn.commit()

    def get_simulation_results(self, limit: int = 50) -> list:
        rows = self._conn.execute(
            "SELECT * FROM simulation_results ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    # --- Settings ---
    def get_setting(self, key: str, default: str = "") -> str:
        row = self._conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self._conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))
        self._conn.commit()