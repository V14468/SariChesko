import time
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QGraphicsOpacityEffect, QFileDialog, QScrollArea,
    QComboBox, QCheckBox, QTextEdit, QGridLayout,
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve

from ...storage.db import get_connection, init_db
from ...storage.repository import Repository
from ...utils.export import export_text_to_file, default_export_dir


ALGO_COLORS = {
    "Leaky Bucket": "#00f0ff",
    "Token Bucket": "#a78bfa",
    "RED": "#f59e0b",
    "CoDel": "#00e5a3",
}

SEVERITY_COLORS = {
    "NONE": "#00e5a3",
    "MILD": "#00f0ff",
    "MODERATE": "#f59e0b",
    "SEVERE": "#f97316",
    "CRITICAL": "#ef4444",
}

ISP_VERDICT_DISPLAY = {
    "healthy": ("Healthy", "#00e5a3"),
    "local_congestion": ("Local Congestion", "#f59e0b"),
    "last_mile": ("Last Mile Issue", "#ef4444"),
    "isp_degradation": ("ISP Degradation", "#f59e0b"),
    "isp_outage": ("ISP Outage", "#ef4444"),
    "dns_issue": ("DNS Issue", "#ef4444"),
}

CONTROL_STYLE = """
QComboBox {
    background-color: #080a10;
    color: #e2e8f0;
    border: 1px solid #1a1d2e;
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 12px;
    font-weight: 600;
}
QComboBox:hover { border-color: #00f0ff; }
QComboBox::drop-down { border: none; width: 24px; }
QCheckBox {
    color: #cbd5e1;
    spacing: 9px;
    font-size: 12px;
    font-weight: 600;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #334155;
    background-color: #05060a;
}
QCheckBox::indicator:checked {
    background-color: #00f0ff;
    border-color: #00f0ff;
}
QTextEdit {
    background-color: #05060a;
    color: #cbd5e1;
    border: 1px solid #121524;
    border-radius: 8px;
    padding: 12px;
    font-family: Consolas, "Cascadia Mono", monospace;
    font-size: 12px;
    selection-background-color: #0c1424;
}
"""


def _fmt_time(ts: float | None) -> str:
    try:
        if ts is None:
            return "No date"
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
    except Exception:
        return "No date"


def _clean(value: str | None, fallback: str = "None") -> str:
    if not value:
        return fallback
    return str(value).replace("_", " ").title()


def _number(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _section_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 11px; font-weight: 800; color: #64748b; letter-spacing: 0.8px;")
    return label


def _small_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 11px; color: #64748b;")
    label.setWordWrap(True)
    return label


def _card() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(20, 16, 20, 16)
    layout.setSpacing(10)
    return frame, layout


class ReportsView(QWidget):
    def __init__(self):
        super().__init__()
        self._diag_rows: list[dict] = []
        self._sim_rows: list[dict] = []
        self._policy_rows: list[dict] = []
        self._recent_measurements: list[dict] = []
        self._latest_report_text = ""

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: #000000; border: none; }")

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Reports")
        title.setStyleSheet("font-size: 26px; font-weight: 800; color: #ffffff;")
        subtitle = QLabel("Build a focused network evidence brief from diagnostics, fixes, and simulations")
        subtitle.setStyleSheet("font-size: 13px; color: #64748b;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_refresh.setFixedHeight(36)
        self._btn_refresh.clicked.connect(self._load_all)
        header.addWidget(self._btn_refresh)

        self._btn_export_report = QPushButton("Export Brief")
        self._btn_export_report.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_export_report.setFixedHeight(36)
        self._btn_export_report.setObjectName("primary_btn")
        self._btn_export_report.clicked.connect(self._export_full_report)
        header.addWidget(self._btn_export_report)
        layout.addLayout(header)

        layout.addWidget(self._build_packet_controls())

        body = QHBoxLayout()
        body.setSpacing(14)

        left_col = QVBoxLayout()
        left_col.setSpacing(14)
        left_col.addWidget(self._build_executive_card())
        left_col.addWidget(self._build_findings_card())
        left_col.addWidget(self._build_preview_card())

        right_col = QVBoxLayout()
        right_col.setSpacing(14)
        right_col.addWidget(self._build_evidence_card())
        right_col.addWidget(self._build_report_shape_card())
        right_col.addStretch()

        body.addLayout(left_col, 3)
        body.addLayout(right_col, 2)
        layout.addLayout(body)
        layout.addStretch()

        scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._anim = QPropertyAnimation(self._opacity, b"opacity")
        self._anim.setDuration(350)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

        self._load_all()

    def showEvent(self, event):
        super().showEvent(event)
        self._load_all()

    def _build_packet_controls(self) -> QFrame:
        card, layout = _card()
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(12)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title_col.addWidget(_section_label("REPORT PACKET"))
        summary = QLabel("Audience, period, and section mix drive the brief below.")
        summary.setStyleSheet("font-size: 12px; color: #64748b;")
        title_col.addWidget(summary)
        top.addLayout(title_col, 1)

        audience_col = QVBoxLayout()
        audience_col.setSpacing(5)
        audience_col.addWidget(_small_label("Audience"))
        self._audience_combo = QComboBox()
        self._audience_combo.addItems(["Operations", "Executive", "Engineering"])
        self._audience_combo.setFixedHeight(34)
        self._audience_combo.setStyleSheet(CONTROL_STYLE)
        self._audience_combo.currentIndexChanged.connect(self._refresh_report)
        audience_col.addWidget(self._audience_combo)
        top.addLayout(audience_col)

        window_col = QVBoxLayout()
        window_col.setSpacing(5)
        window_col.addWidget(_small_label("Window"))
        self._window_combo = QComboBox()
        self._window_combo.addItem("Last 7 days", 7)
        self._window_combo.addItem("Last 30 days", 30)
        self._window_combo.addItem("Last 90 days", 90)
        self._window_combo.addItem("All time", 0)
        self._window_combo.setCurrentIndex(1)
        self._window_combo.setFixedHeight(34)
        self._window_combo.setStyleSheet(CONTROL_STYLE)
        self._window_combo.currentIndexChanged.connect(self._refresh_report)
        window_col.addWidget(self._window_combo)
        top.addLayout(window_col)

        layout.addLayout(top)

        checks = QHBoxLayout()
        checks.setSpacing(16)
        self._section_checks: dict[str, QCheckBox] = {}
        for key, text in [
            ("summary", "Executive brief"),
            ("findings", "Top findings"),
            ("fixes", "Fix audit"),
            ("simulations", "Simulation proof"),
            ("evidence", "Evidence ledger"),
        ]:
            cb = QCheckBox(text)
            cb.setChecked(True)
            cb.setStyleSheet(CONTROL_STYLE)
            cb.stateChanged.connect(self._refresh_report)
            self._section_checks[key] = cb
            checks.addWidget(cb)
        checks.addStretch()
        layout.addLayout(checks)
        return card

    def _build_executive_card(self) -> QFrame:
        card, layout = _card()
        layout.addWidget(_section_label("EXECUTIVE BRIEF"))

        headline = QHBoxLayout()
        headline.setSpacing(14)
        self._brief_verdict = QLabel("No Evidence")
        self._brief_verdict.setStyleSheet("font-size: 28px; font-weight: 900; color: #64748b;")
        headline.addWidget(self._brief_verdict, 1)

        score_box = QVBoxLayout()
        score_box.setSpacing(2)
        score_box.addWidget(_small_label("Report readiness"))
        self._readiness_score = QLabel("0%")
        self._readiness_score.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._readiness_score.setStyleSheet("font-size: 28px; font-weight: 900; color: #00f0ff;")
        score_box.addWidget(self._readiness_score)
        headline.addLayout(score_box)
        layout.addLayout(headline)

        self._brief_narrative = QLabel("Run diagnostics or simulations to generate a report brief.")
        self._brief_narrative.setWordWrap(True)
        self._brief_narrative.setStyleSheet("font-size: 13px; color: #cbd5e1; line-height: 1.5;")
        layout.addWidget(self._brief_narrative)

        grid = QGridLayout()
        grid.setSpacing(10)
        self._brief_metrics: dict[str, QLabel] = {}
        for idx, key in enumerate(("score", "signal", "isp", "recommendation")):
            mini = QFrame()
            mini.setStyleSheet("""
                QFrame {
                    background-color: #080a10;
                    border: 1px solid #121524;
                    border-radius: 8px;
                    padding: 10px;
                }
            """)
            ml = QVBoxLayout(mini)
            ml.setContentsMargins(12, 10, 12, 10)
            ml.setSpacing(4)
            label = QLabel(key.replace("_", " ").upper())
            label.setStyleSheet("font-size: 10px; font-weight: 800; color: #475569; letter-spacing: 0.6px;")
            value = QLabel("No data")
            value.setWordWrap(True)
            value.setStyleSheet("font-size: 13px; font-weight: 800; color: #e2e8f0;")
            ml.addWidget(label)
            ml.addWidget(value)
            self._brief_metrics[key] = value
            grid.addWidget(mini, idx // 2, idx % 2)
        layout.addLayout(grid)
        return card

    def _build_findings_card(self) -> QFrame:
        card, layout = _card()
        layout.addWidget(_section_label("TOP FINDINGS"))
        self._findings_layout = QVBoxLayout()
        self._findings_layout.setSpacing(8)
        layout.addLayout(self._findings_layout)
        return card

    def _build_preview_card(self) -> QFrame:
        card, layout = _card()
        heading = QHBoxLayout()
        heading.addWidget(_section_label("MARKDOWN PREVIEW"))
        heading.addStretch()
        self._generated_at = QLabel("Not generated")
        self._generated_at.setStyleSheet("font-size: 11px; color: #475569;")
        heading.addWidget(self._generated_at)
        layout.addLayout(heading)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setMinimumHeight(300)
        self._preview.setStyleSheet(CONTROL_STYLE)
        layout.addWidget(self._preview)
        return card

    def _build_evidence_card(self) -> QFrame:
        card, layout = _card()
        layout.addWidget(_section_label("EVIDENCE INVENTORY"))

        self._evidence_window = QLabel("No window selected")
        self._evidence_window.setStyleSheet("font-size: 12px; color: #64748b;")
        layout.addWidget(self._evidence_window)

        self._evidence_values: dict[str, QLabel] = {}
        for key, label in [
            ("diagnostics", "Diagnostic runs"),
            ("simulations", "Simulation runs"),
            ("fixes", "Applied fixes"),
            ("measurements", "Latest samples"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(10)
            name = QLabel(label)
            name.setStyleSheet("font-size: 13px; font-weight: 700; color: #e2e8f0;")
            value = QLabel("0")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            value.setStyleSheet("font-size: 16px; font-weight: 900; color: #00f0ff;")
            row.addWidget(name)
            row.addStretch()
            row.addWidget(value)
            layout.addLayout(row)
            self._evidence_values[key] = value

        self._data_span_label = _small_label("No stored evidence yet.")
        layout.addWidget(self._data_span_label)
        return card

    def _build_report_shape_card(self) -> QFrame:
        card, layout = _card()
        layout.addWidget(_section_label("REPORT SHAPE"))

        self._shape_labels: dict[str, QLabel] = {}
        for key, title in [
            ("audience", "Audience lens"),
            ("priority", "Primary risk"),
            ("action", "Next action"),
            ("export", "Export payload"),
        ]:
            label = QLabel(title.upper())
            label.setStyleSheet("font-size: 10px; font-weight: 800; color: #475569; letter-spacing: 0.7px;")
            value = QLabel("No data")
            value.setWordWrap(True)
            value.setStyleSheet("font-size: 13px; color: #cbd5e1;")
            layout.addWidget(label)
            layout.addWidget(value)
            self._shape_labels[key] = value

        return card

    def _load_all(self):
        try:
            conn = get_connection()
            init_db(conn)
            repo = Repository(conn)
            self._diag_rows = repo.get_diagnostic_runs(limit=500)
            self._sim_rows = repo.get_simulation_results(limit=500)
            self._policy_rows = repo.get_applied_policies(limit=500)
            self._recent_measurements = []
            if self._diag_rows:
                session_id = self._diag_rows[0].get("session_id")
                if session_id:
                    self._recent_measurements = repo.get_recent_measurements(session_id, limit=200)
            conn.close()
        except Exception:
            self._diag_rows = []
            self._sim_rows = []
            self._policy_rows = []
            self._recent_measurements = []

        self._refresh_report()

    def _refresh_report(self):
        analysis = self._analyze_current_packet()
        self._populate_brief(analysis)
        self._populate_findings(analysis)
        self._populate_evidence(analysis)
        self._populate_shape(analysis)
        self._latest_report_text = self._build_report_text(analysis)
        self._preview.setPlainText(self._latest_report_text)
        self._generated_at.setText(f"Generated {_fmt_time(time.time())}")

    def _window_days(self) -> int:
        return int(self._window_combo.currentData() or 0)

    def _filter_by_window(self, rows: list[dict]) -> list[dict]:
        days = self._window_days()
        if days <= 0:
            return list(rows)
        cutoff = time.time() - (days * 86400)
        return [r for r in rows if _number(r.get("timestamp")) >= cutoff]

    def _window_label(self) -> str:
        return self._window_combo.currentText()

    def _checked(self, key: str) -> bool:
        return self._section_checks[key].isChecked()

    def _analyze_current_packet(self) -> dict:
        diags = self._filter_by_window(self._diag_rows)
        sims = self._filter_by_window(self._sim_rows)
        fixes = self._filter_by_window(self._policy_rows)
        latest = diags[0] if diags else (self._diag_rows[0] if self._diag_rows else None)

        scores = [_number(r.get("congestion_score")) for r in diags]
        avg_score = _avg(scores)
        max_score = max(scores) if scores else None
        high_runs = sum(1 for r in diags if (r.get("severity") or "NONE") in ("SEVERE", "CRITICAL"))

        severity_order = {"NONE": 0, "MILD": 1, "MODERATE": 2, "SEVERE": 3, "CRITICAL": 4}
        highest_severity = "NONE"
        for row in diags:
            sev = row.get("severity") or "NONE"
            if severity_order.get(sev, 0) > severity_order.get(highest_severity, 0):
                highest_severity = sev

        degraded_isp = [
            r for r in diags
            if (r.get("isp_verdict") or "") not in ("", "healthy", "local_congestion")
        ]
        fixes_verified = [
            p for p in fixes
            if p.get("score_after") is not None and _number(p.get("score_after")) < _number(p.get("score_before"))
        ]
        rollbacks = [p for p in fixes if p.get("rolled_back_at")]

        readiness = 0
        if diags:
            readiness += 40
        if self._recent_measurements:
            readiness += 15
        if sims:
            readiness += 20
        if fixes:
            readiness += 15
        if len(diags) >= 3:
            readiness += 10

        if not diags and not sims and not fixes:
            verdict = "No Evidence"
            color = "#64748b"
        elif highest_severity in ("SEVERE", "CRITICAL") or degraded_isp:
            verdict = "Action Needed"
            color = "#ef4444" if highest_severity == "CRITICAL" else "#f97316"
        elif highest_severity == "MODERATE":
            verdict = "Watch Closely"
            color = "#f59e0b"
        else:
            verdict = "Stable"
            color = "#00e5a3"

        span_times = [
            _number(r.get("timestamp")) for r in (diags + sims + fixes)
            if r.get("timestamp") is not None
        ]
        span = "No dated evidence"
        if span_times:
            span = f"{_fmt_time(min(span_times))} to {_fmt_time(max(span_times))}"

        return {
            "audience": self._audience_combo.currentText(),
            "window": self._window_label(),
            "diags": diags,
            "sims": sims,
            "fixes": fixes,
            "latest": latest,
            "avg_score": avg_score,
            "max_score": max_score,
            "highest_severity": highest_severity,
            "high_runs": high_runs,
            "degraded_isp": degraded_isp,
            "fixes_verified": fixes_verified,
            "rollbacks": rollbacks,
            "readiness": min(readiness, 100),
            "verdict": verdict,
            "verdict_color": color,
            "span": span,
            "findings": self._make_findings(
                diags, sims, fixes, latest, avg_score, high_runs,
                degraded_isp, fixes_verified, rollbacks
            ),
        }

    def _make_findings(
        self,
        diags: list[dict],
        sims: list[dict],
        fixes: list[dict],
        latest: dict | None,
        avg_score: float | None,
        high_runs: int,
        degraded_isp: list[dict],
        fixes_verified: list[dict],
        rollbacks: list[dict],
    ) -> list[tuple[str, str, str]]:
        findings: list[tuple[str, str, str]] = []
        if latest:
            sev = latest.get("severity") or "NONE"
            score = _number(latest.get("congestion_score"))
            signal = _clean(latest.get("dominant_signal"), "No dominant signal")
            findings.append((
                f"Latest diagnostic is {sev}",
                f"Score {score:.0f}; dominant signal: {signal}.",
                SEVERITY_COLORS.get(sev, "#64748b"),
            ))
        if avg_score is not None:
            findings.append((
                "Period congestion average",
                f"{avg_score:.1f} across {len(diags)} diagnostic run(s).",
                "#00f0ff" if avg_score < 20 else "#f59e0b",
            ))
        if high_runs:
            findings.append((
                "Elevated runs need attention",
                f"{high_runs} run(s) landed in HIGH or CRITICAL severity.",
                "#ef4444",
            ))
        if degraded_isp:
            verdict_text, _ = ISP_VERDICT_DISPLAY.get(
                degraded_isp[0].get("isp_verdict") or "",
                (_clean(degraded_isp[0].get("isp_verdict"), "Unknown"), "#ef4444"),
            )
            findings.append((
                "ISP path degradation detected",
                f"{verdict_text} appears in {len(degraded_isp)} diagnostic run(s).",
                "#f97316",
            ))
        if fixes_verified:
            findings.append((
                "Fix impact is measurable",
                f"{len(fixes_verified)} applied fix(es) have lower after-scores than before-scores.",
                "#00e5a3",
            ))
        if rollbacks:
            findings.append((
                "Rollback history exists",
                f"{len(rollbacks)} policy change(s) were rolled back.",
                "#f59e0b",
            ))
        if sims:
            best = max(sims, key=lambda r: _number(r.get("throughput_mbps")))
            findings.append((
                "Best simulated throughput",
                f"{best.get('algorithm') or 'Unknown'} reached "
                f"{_number(best.get('throughput_mbps')):.2f} Mbps in "
                f"{_clean(best.get('scenario'), 'Unknown scenario')}.",
                ALGO_COLORS.get(best.get("algorithm"), "#a78bfa"),
            ))
        if not findings:
            findings.append((
                "No report evidence yet",
                "Run a diagnostic, simulation, or approved fix to seed this brief.",
                "#64748b",
            ))
        return findings[:5]

    def _populate_brief(self, analysis: dict):
        self._brief_verdict.setText(analysis["verdict"])
        self._brief_verdict.setStyleSheet(
            f"font-size: 28px; font-weight: 900; color: {analysis['verdict_color']};"
        )
        self._readiness_score.setText(f"{analysis['readiness']}%")

        latest = analysis["latest"]
        if latest:
            score = _number(latest.get("congestion_score"))
            sev = latest.get("severity") or "NONE"
            signal = _clean(latest.get("dominant_signal"), "No dominant signal")
            algo = latest.get("recommended_algo") or "No algorithm needed"
            verdict_text, _ = ISP_VERDICT_DISPLAY.get(
                latest.get("isp_verdict") or "",
                (_clean(latest.get("isp_verdict"), "Unknown"), "#64748b"),
            )
            self._brief_narrative.setText(
                f"For {analysis['window'].lower()}, the report packet reads as {analysis['verdict'].lower()}. "
                f"The latest diagnostic scored {score:.0f} with {sev} severity, led by {signal}. "
                f"ISP status is {verdict_text}; recommended treatment is {algo}."
            )
            self._brief_metrics["score"].setText(f"{score:.0f} / {sev}")
            self._brief_metrics["signal"].setText(signal)
            self._brief_metrics["isp"].setText(verdict_text)
            self._brief_metrics["recommendation"].setText(algo)
        else:
            self._brief_narrative.setText("No diagnostics are available in this packet yet.")
            for value in self._brief_metrics.values():
                value.setText("No data")

    def _populate_findings(self, analysis: dict):
        while self._findings_layout.count():
            item = self._findings_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for title, body, color in analysis["findings"]:
            frame = QFrame()
            frame.setStyleSheet(f"""
                QFrame {{
                    background-color: #080a10;
                    border: 1px solid #121524;
                    border-left: 4px solid {color};
                    border-radius: 8px;
                }}
            """)
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(14, 10, 14, 10)
            layout.setSpacing(4)
            t = QLabel(title)
            t.setStyleSheet("font-size: 13px; font-weight: 800; color: #ffffff;")
            b = QLabel(body)
            b.setWordWrap(True)
            b.setStyleSheet("font-size: 12px; color: #94a3b8;")
            layout.addWidget(t)
            layout.addWidget(b)
            self._findings_layout.addWidget(frame)

    def _populate_evidence(self, analysis: dict):
        self._evidence_window.setText(f"{analysis['window']} - {analysis['span']}")
        self._evidence_values["diagnostics"].setText(str(len(analysis["diags"])))
        self._evidence_values["simulations"].setText(str(len(analysis["sims"])))
        self._evidence_values["fixes"].setText(str(len(analysis["fixes"])))
        self._evidence_values["measurements"].setText(str(len(self._recent_measurements)))
        self._data_span_label.setText(
            f"Export readiness is {analysis['readiness']}%. "
            f"The packet uses {len(analysis['diags']) + len(analysis['sims']) + len(analysis['fixes'])} stored event(s)."
        )

    def _populate_shape(self, analysis: dict):
        audience = analysis["audience"]
        latest = analysis["latest"]
        primary = "No active risk"
        action = "Collect fresh diagnostic evidence"
        if latest:
            primary = _clean(latest.get("dominant_signal"), "Unclassified congestion")
            algo = latest.get("recommended_algo")
            if algo:
                action = f"Review {algo} before applying policy changes"
            elif analysis["verdict"] == "Stable":
                action = "Keep monitoring; no policy change is indicated"
            else:
                action = "Investigate elevated diagnostic signals"

        sections = [cb.text() for cb in self._section_checks.values() if cb.isChecked()]
        self._shape_labels["audience"].setText(f"{audience} language and priority framing")
        self._shape_labels["priority"].setText(primary)
        self._shape_labels["action"].setText(action)
        self._shape_labels["export"].setText(", ".join(sections) if sections else "No sections selected")

    def _build_report_text(self, analysis: dict) -> str:
        lines = [
            "# SariChesko Network Evidence Brief",
            f"Generated: {_fmt_time(time.time())}",
            f"Audience: {analysis['audience']}",
            f"Window: {analysis['window']}",
            "",
        ]

        if self._checked("summary"):
            lines.extend([
                "## Executive Brief",
                f"Verdict: {analysis['verdict']}",
                f"Report readiness: {analysis['readiness']}%",
                f"Evidence span: {analysis['span']}",
                "",
            ])
            latest = analysis["latest"]
            if latest:
                verdict_text, _ = ISP_VERDICT_DISPLAY.get(
                    latest.get("isp_verdict") or "",
                    (_clean(latest.get("isp_verdict"), "Unknown"), "#64748b"),
                )
                lines.extend([
                    f"- Latest run: {_fmt_time(latest.get('timestamp'))}",
                    f"- Congestion score: {_number(latest.get('congestion_score')):.0f}",
                    f"- Severity: {latest.get('severity') or 'NONE'}",
                    f"- Dominant signal: {_clean(latest.get('dominant_signal'), 'None')}",
                    f"- ISP status: {verdict_text}",
                    f"- Recommendation: {latest.get('recommended_algo') or 'No algorithm needed'}",
                    f"- Reason: {latest.get('recommendation_reason') or 'No reason recorded'}",
                    "",
                ])
            else:
                lines.extend(["No diagnostic runs are available for this packet.", ""])

        if self._checked("findings"):
            lines.extend(["## Top Findings", ""])
            for title, body, _ in analysis["findings"]:
                lines.append(f"- {title}: {body}")
            lines.append("")

        if self._checked("fixes"):
            lines.extend(["## Fix Audit", ""])
            if analysis["fixes"]:
                for row in analysis["fixes"][:10]:
                    after = row.get("score_after")
                    after_text = f"{_number(after):.0f}" if after is not None else "Not verified"
                    rolled_back = "yes" if row.get("rolled_back_at") else "no"
                    lines.append(
                        f"- {_fmt_time(row.get('timestamp'))}: {row.get('algorithm') or 'Unknown'} "
                        f"on {row.get('interface') or 'unknown interface'}; "
                        f"score {_number(row.get('score_before')):.0f} -> {after_text}; "
                        f"rolled back: {rolled_back}."
                    )
            else:
                lines.append("No applied fixes are in this packet.")
            lines.append("")

        if self._checked("simulations"):
            lines.extend(["## Simulation Proof", ""])
            if analysis["sims"]:
                ranked = sorted(
                    analysis["sims"],
                    key=lambda r: (
                        _number(r.get("throughput_mbps")),
                        -_number(r.get("avg_latency_ms")),
                    ),
                    reverse=True,
                )
                for row in ranked[:10]:
                    lines.append(
                        f"- {_clean(row.get('scenario'), 'Scenario')}: {row.get('algorithm') or 'Unknown'} "
                        f"delivered {_number(row.get('throughput_mbps')):.2f} Mbps, "
                        f"{_number(row.get('avg_latency_ms')):.1f} ms latency, "
                        f"{_number(row.get('loss_pct')):.2f}% loss."
                    )
            else:
                lines.append("No simulation runs are in this packet.")
            lines.append("")

        if self._checked("evidence"):
            lines.extend([
                "## Evidence Ledger",
                f"- Diagnostic runs: {len(analysis['diags'])}",
                f"- Simulation runs: {len(analysis['sims'])}",
                f"- Applied fixes: {len(analysis['fixes'])}",
                f"- Latest measurement samples: {len(self._recent_measurements)}",
                "",
            ])

        return "\n".join(lines).strip() + "\n"

    def _export_full_report(self):
        if not self._latest_report_text.strip():
            return

        default_name = str(default_export_dir() / f"network_brief_{int(time.time())}.md")
        path, _ = QFileDialog.getSaveFileName(self, "Export Brief", default_name, "Markdown Files (*.md)")
        if not path:
            return
        try:
            export_text_to_file(self._latest_report_text, path)
        except Exception:
            pass
