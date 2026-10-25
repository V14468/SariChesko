"""Theme screenshot generator for SariChesko.

Renders Welcome screen, all 8 tabs, PermissionDialog and RollbackDialog offscreen
at 1440x920 using a seeded database with fixed timestamps, saving PNGs to:
theme_check/<theme>/
"""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# Set offscreen Qt platform before importing Qt
os.environ["QT_QPA_PLATFORM"] = "offscreen"

# Ensure repository root is on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize

from sarichesko.storage.db import init_db, get_connection
from sarichesko.storage.repository import Repository
from sarichesko.storage.models import (
    Session,
    Measurement,
    ISPDiagnostic,
    DiagnosticRun,
    AppliedPolicy,
    SimulationResult as SimResultModel,
)
from sarichesko.core.recommendation_engine import (
    Algorithm,
    Recommendation,
    TrafficProfile,
)
from sarichesko.core.congestion_scorer import CongestionScore
from sarichesko.core.isp_probe import ISPVerdict, ISPDiagnosticResult
from sarichesko.core.diagnostics_engine import DiagnosticResult
from sarichesko.simulation.engine_base import (
    SimConfig,
    AlgorithmType,
    SimMetrics,
    SimulationResult as SimResultObj,
)
from sarichesko.ui.main_window import MainWindow, NAV_ITEMS
from sarichesko.ui.widgets.permission_dialog import PermissionDialog
from sarichesko.ui.widgets.rollback_dialog import RollbackDialog
from sarichesko.ui.theme import OLED_BLACK_THEME


BASE_TIME = 1770000000.0


def seed_database(conn):
    """Seed fixed deterministic data for reproducible screenshots."""
    init_db(conn)
    repo = Repository(conn)

    session_id = "session-seed-001"
    repo.save_session(
        Session(
            id=session_id,
            started_at=BASE_TIME - 3600,
            ended_at=BASE_TIME - 3000,
            interface="eth0",
            mode="diagnostic",
        )
    )

    measurements = []
    for i in range(10):
        m = Measurement(
            session_id=session_id,
            timestamp=BASE_TIME - 3600 + i * 60,
            bandwidth_mbps=85.0 + i * 0.5,
            latency_ms=45.0 + i * 2.0,
            jitter_ms=3.5,
            packet_loss_pct=1.2,
            utilization_pct=75.0,
            queue_delay_ms=25.0,
        )
        repo.save_measurement(m)
        measurements.append(m)

    repo.save_isp_diagnostic(
        ISPDiagnostic(
            session_id=session_id,
            timestamp=BASE_TIME - 3500,
            verdict="local_congestion",
            details="Local bottleneck detected at default gateway",
            gateway_ms=18.5,
            isp_hop_ms=42.0,
            wan_ms=65.0,
            dns_ok=True,
        )
    )

    diag_id = "diag-seed-001"
    repo.save_diagnostic_run(
        DiagnosticRun(
            id=diag_id,
            session_id=session_id,
            timestamp=BASE_TIME - 3500,
            congestion_score=78.5,
            severity="SEVERE",
            dominant_signal="bufferbloat",
            isp_verdict="local_congestion",
            recommended_algo="CoDel",
            recommendation_reason="Severe bufferbloat detected with high queuing delay; CoDel mitigates bufferbloat without bandwidth loss.",
            confidence="HIGH",
        )
    )

    repo.save_applied_policy(
        AppliedPolicy(
            id="fix-seed-001",
            diagnostic_id=diag_id,
            timestamp=BASE_TIME - 3000,
            interface="eth0",
            algorithm="CoDel",
            parameters=json.dumps({"target_ms": 5, "interval_ms": 100, "limit": 1000}),
            snapshot_before="default pfifo_fast",
            score_before=78.5,
            score_after=18.2,
            verdict="improved",
            rolled_back_at=None,
        )
    )

    algos = [
        ("Leaky Bucket", 9.5, 42.0, 0.5, 0.98),
        ("Token Bucket", 9.8, 38.0, 0.8, 0.95),
        ("RED", 8.9, 28.0, 2.1, 0.92),
        ("CoDel", 9.7, 18.5, 0.2, 0.99),
    ]
    for idx, (algo_name, bw, lat, loss, fair) in enumerate(algos):
        repo.save_simulation_result(
            SimResultModel(
                id=f"sim-seed-{idx}",
                timestamp=BASE_TIME - 2000 + idx * 100,
                scenario="bursty_traffic",
                algorithm=algo_name,
                engine_used="Built-in Python",
                parameters=json.dumps({"queue_size": 100, "link_mbps": 10.0, "duration_s": 10.0}),
                throughput_mbps=bw,
                avg_latency_ms=lat,
                loss_pct=loss,
                fairness_index=fair,
                metrics_detail=json.dumps({"max_latency": lat * 1.5, "max_queue": 85}),
            )
        )

    return measurements, diag_id


def settle_event_loop(app, ticks=20):
    """Process event loop ticks to ensure animations, layouts and styles settle."""
    for _ in range(ticks):
        app.processEvents()


def capture_screenshots(theme_name: str):
    temp_dir = tempfile.mkdtemp(prefix="sarichesko_theme_shots_")
    os.environ["APPDATA"] = temp_dir

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    # Apply real app stylesheet
    # If theme_manager is available (Stage 1+), use it; otherwise use legacy theme
    try:
        from sarichesko.ui.theme import theme_manager, build_stylesheet
        if theme_name in ("light", "light_theme"):
            theme_manager.set_theme("light")
        else:
            theme_manager.set_theme("dark")
    except (ImportError, AttributeError):
        app.setStyleSheet(OLED_BLACK_THEME)

    conn = get_connection()
    measurements, diag_id = seed_database(conn)
    conn.close()

    out_dir = ROOT_DIR / "theme_check" / theme_name
    out_dir.mkdir(parents=True, exist_ok=True)

    window = MainWindow()
    window.setFixedSize(1440, 920)
    window.show()
    settle_event_loop(app, 25)

    # Helper to grab and save
    def save_shot(widget, filename):
        settle_event_loop(app, 20)
        pixmap = widget.grab()
        path = out_dir / filename
        pixmap.save(str(path))
        print(f"  [SAVED] {path.relative_to(ROOT_DIR)} ({pixmap.width()}x{pixmap.height()})")

    # 00 Welcome screen
    window._show_welcome()
    save_shot(window, "00_welcome.png")

    # 01 Dashboard
    window._navigate(1, window._nav_buttons[0])
    dashboard_view = window._stack.widget(1)
    if hasattr(dashboard_view, "_load_latest"):
        dashboard_view._load_latest()
    save_shot(window, "01_dashboard.png")

    # 02 Diagnose
    window._navigate(2, window._nav_buttons[1])
    diagnose_view = window._stack.widget(2)
    rec = Recommendation(
        algo=Algorithm.CODEL,
        parameters={"target_ms": 5, "interval_ms": 100, "limit": 1000},
        reason="Severe bufferbloat detected with high queuing delay; CoDel mitigates bufferbloat without bandwidth loss.",
        confidence="HIGH",
        actions=["Deploy CoDel on eth0", "Verify queuing latency drop"],
    )
    score = CongestionScore(
        score=78.5,
        severity="SEVERE",
        signals={"bufferbloat": 0.85, "latency_inflation": 0.72},
        dominant_signal="bufferbloat",
        is_persistent=True,
        trend="worsening",
    )
    isp_res = ISPDiagnosticResult(
        timestamp=BASE_TIME - 3500,
        verdict=ISPVerdict.LOCAL_CONGESTION,
        gateway_latency_ms=18.5,
        isp_hop_latency_ms=42.0,
        wan_latency_ms=65.0,
        dns_ok=True,
        details="Local bottleneck detected at default gateway",
        probe_results=[],
    )
    prof = TrafficProfile(
        is_bursty=True,
        burst_tolerance="HIGH",
        needs_smooth_output=False,
        queue_growth_rate=65.0,
        sojourn_time_ms=55.0,
        dominant_signal="bufferbloat",
    )
    diag_result = DiagnosticResult(
        id=diag_id,
        timestamp=BASE_TIME - 3500,
        congestion_score=score,
        isp_result=isp_res,
        traffic_profile=prof,
        recommendation=rec,
        measurements=measurements,
    )
    if hasattr(diagnose_view, "_on_complete"):
        diagnose_view._on_complete(diag_result)
    save_shot(window, "02_diagnose.png")

    # 03 Live Network
    window._navigate(3, window._nav_buttons[2])
    save_shot(window, "03_live_network.png")

    # 04 Simulation Lab
    window._navigate(4, window._nav_buttons[3])
    sim_lab_view = window._stack.widget(4)
    sim_cfg = SimConfig(scenario="bursty_traffic", algorithm=AlgorithmType.CODEL, duration_s=10.0)
    sim_metrics = SimMetrics(
        throughput_mbps=9.7,
        avg_latency_ms=18.5,
        max_latency_ms=28.0,
        loss_pct=0.2,
        avg_queue_depth=15.0,
        max_queue_depth=45,
        fairness_index=0.99,
        total_packets=5000,
        dropped_packets=10,
        delivered_packets=4990,
    )
    sim_result = SimResultObj(
        scenario="bursty_traffic",
        algorithm="CoDel",
        config=sim_cfg,
        duration_s=10.0,
        metrics=sim_metrics,
        queue_depth_over_time=[(t * 0.05, int(15 + 10 * (t % 7))) for t in range(200)],
        latency_over_time=[(t * 0.05, 15.0 + 5.0 * (t % 5)) for t in range(200)],
        engine_used="Built-in Python",
    )
    if hasattr(sim_lab_view, "_on_complete"):
        sim_lab_view._on_complete(sim_result)
    save_shot(window, "04_simulation_lab.png")

    # 05 Compare
    window._navigate(5, window._nav_buttons[4])
    compare_view = window._stack.widget(5)
    compare_results = {}
    for algo_enum, bw, lat, loss, fair in [
        (AlgorithmType.LEAKY_BUCKET, 9.5, 42.0, 0.5, 0.98),
        (AlgorithmType.TOKEN_BUCKET, 9.8, 38.0, 0.8, 0.95),
        (AlgorithmType.RED, 8.9, 28.0, 2.1, 0.92),
        (AlgorithmType.CODEL, 9.7, 18.5, 0.2, 0.99),
    ]:
        cfg = SimConfig(scenario="bursty_traffic", algorithm=algo_enum, duration_s=10.0)
        m = SimMetrics(
            throughput_mbps=bw,
            avg_latency_ms=lat,
            max_latency_ms=lat * 1.5,
            loss_pct=loss,
            avg_queue_depth=20.0,
            max_queue_depth=50,
            fairness_index=fair,
            total_packets=5000,
            dropped_packets=int(5000 * loss / 100),
            delivered_packets=5000 - int(5000 * loss / 100),
        )
        compare_results[algo_enum.value] = SimResultObj(
            scenario="bursty_traffic",
            algorithm=algo_enum.value,
            config=cfg,
            duration_s=10.0,
            metrics=m,
            engine_used="Built-in Python",
        )
    if hasattr(compare_view, "_on_complete"):
        compare_view._on_complete(compare_results)
    save_shot(window, "05_compare.png")

    # 06 History
    window._navigate(6, window._nav_buttons[5])
    history_view = window._stack.widget(6)
    if hasattr(history_view, "_load_all"):
        history_view._load_all()
    save_shot(window, "06_history.png")

    # 07 Reports
    window._navigate(7, window._nav_buttons[6])
    reports_view = window._stack.widget(7)
    if hasattr(reports_view, "_generate"):
        reports_view._generate()
    save_shot(window, "07_reports.png")

    # 08 Settings
    window._navigate(8, window._nav_buttons[7])
    save_shot(window, "08_settings.png")

    # 09 PermissionDialog
    perm_dialog = PermissionDialog(
        iface="eth0",
        algo=Algorithm.CODEL,
        parameters={"target_ms": 5, "interval_ms": 100, "limit": 1000},
        reason="Severe bufferbloat detected with high queuing delay; CoDel mitigates bufferbloat without bandwidth loss.",
        congestion_score=78.5,
        severity="SEVERE",
        supported=True,
        requires_elevation=False,
    )
    perm_dialog.setFixedSize(1440, 920)
    perm_dialog.show()
    save_shot(perm_dialog, "09_permission_dialog.png")
    perm_dialog.close()

    # 10 RollbackDialog
    rollback_dialog = RollbackDialog(
        algo_name="CoDel",
        score_before=78.5,
        score_after=18.2,
        verdict="improved",
        latency_before=85.0,
        latency_after=12.5,
        loss_before=4.2,
        loss_after=0.1,
        apply_message="CoDel queue discipline applied to eth0.",
    )
    rollback_dialog.setFixedSize(1440, 920)
    rollback_dialog.show()
    save_shot(rollback_dialog, "10_rollback_dialog.png")
    rollback_dialog.close()

    window.close()
    settle_event_loop(app, 10)
    print(f"All 11 screenshots successfully captured into theme_check/{theme_name}/")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate UI theme screenshots")
    parser.add_argument("--theme", default="baseline_dark", help="Theme output directory name")
    args = parser.parse_args()
    capture_screenshots(args.theme)
