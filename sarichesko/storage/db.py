import sqlite3
import os
from pathlib import Path


def get_db_path() -> Path:
    data_dir = Path(os.environ.get("APPDATA") or Path.home() / ".local" / "share") / "SariChesko"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "sarichesko.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            started_at  REAL NOT NULL,
            ended_at    REAL,
            interface   TEXT,
            mode        TEXT NOT NULL DEFAULT 'real'
        );

        CREATE TABLE IF NOT EXISTS measurements (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      TEXT REFERENCES sessions(id),
            timestamp       REAL NOT NULL,
            bandwidth_mbps  REAL,
            latency_ms      REAL,
            jitter_ms       REAL,
            packet_loss_pct REAL,
            utilization_pct REAL,
            queue_delay_ms  REAL
        );

        CREATE TABLE IF NOT EXISTS baselines (
            interface           TEXT PRIMARY KEY,
            measured_at         REAL NOT NULL,
            latency_mean_ms     REAL,
            latency_stddev_ms   REAL,
            loss_mean_pct       REAL,
            bandwidth_mean_mbps REAL,
            jitter_mean_ms      REAL
        );

        CREATE TABLE IF NOT EXISTS isp_diagnostics (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id  TEXT REFERENCES sessions(id),
            timestamp   REAL NOT NULL,
            verdict     TEXT,
            gateway_ms  REAL,
            isp_hop_ms  REAL,
            wan_ms      REAL,
            dns_ok      INTEGER,
            details     TEXT
        );

        CREATE TABLE IF NOT EXISTS diagnostic_runs (
            id                      TEXT PRIMARY KEY,
            session_id              TEXT REFERENCES sessions(id),
            timestamp               REAL NOT NULL,
            congestion_score        REAL,
            severity                TEXT,
            dominant_signal         TEXT,
            isp_verdict             TEXT,
            recommended_algo        TEXT,
            recommendation_reason   TEXT,
            confidence              TEXT
        );

        CREATE TABLE IF NOT EXISTS applied_policies (
            id              TEXT PRIMARY KEY,
            diagnostic_id   TEXT,
            timestamp       REAL NOT NULL,
            interface       TEXT,
            algorithm       TEXT,
            parameters      TEXT,
            snapshot_before TEXT,
            score_before    REAL,
            score_after     REAL,
            verdict         TEXT,
            rolled_back_at  REAL
        );

        CREATE TABLE IF NOT EXISTS simulation_results (
            id              TEXT PRIMARY KEY,
            timestamp       REAL NOT NULL,
            scenario        TEXT,
            algorithm       TEXT,
            parameters      TEXT,
            engine_used     TEXT,
            throughput_mbps REAL,
            avg_latency_ms  REAL,
            loss_pct        REAL,
            fairness_index  REAL,
            metrics_detail  TEXT
        );

        CREATE TABLE IF NOT EXISTS settings (
            key     TEXT PRIMARY KEY,
            value   TEXT
        );
    """)
    conn.commit()