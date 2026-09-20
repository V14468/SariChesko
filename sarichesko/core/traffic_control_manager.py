"""Orchestrates the human-in-the-loop "apply a fix" workflow:

  save a rollback snapshot -> apply the recommended policy -> re-run a real
  diagnostic to verify the after-state -> persist the before/after result.

This module never applies anything on its own initiative -- it's only ever
invoked after the person has explicitly approved a specific recommendation
in a PermissionDialog. Nothing here silently changes network settings.
"""
import json
import time
import uuid
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QThread, Signal

from ..platform import get_controller
from ..platform.base import ApplyResult, ConfigSnapshot
from ..storage.db import get_connection, init_db
from ..storage.repository import Repository
from ..storage.models import AppliedPolicy
from .recommendation_engine import Algorithm
from .diagnostics_engine import DiagnosticsWorker, DiagnosticResult


IMPROVEMENT_THRESHOLD = 0.10  # 10% relative change in congestion score counts as a real shift


def verdict_for(score_before: float, score_after: float) -> str:
    if score_before <= 0:
        return "no_change"
    delta = (score_before - score_after) / score_before
    if delta >= IMPROVEMENT_THRESHOLD:
        return "improved"
    if delta <= -IMPROVEMENT_THRESHOLD:
        return "worse"
    return "no_change"


@dataclass
class ApplyFixReport:
    applied: bool
    policy_id: Optional[str]
    apply_message: str
    snapshot: Optional[ConfigSnapshot]
    score_before: float
    score_after: Optional[float]
    verdict: Optional[str]
    latency_before_ms: Optional[float] = None
    latency_after_ms: Optional[float] = None
    loss_before_pct: Optional[float] = None
    loss_after_pct: Optional[float] = None
    after_result: Optional[DiagnosticResult] = None


class ApplyFixWorker(QThread):
    """Applies one recommended policy to one interface, then immediately
    re-measures using the same DiagnosticsWorker pipeline used elsewhere in
    the app, so the "after" numbers are directly comparable to the "before"
    numbers the recommendation was based on."""

    progress = Signal(str, int)
    complete = Signal(object)   # ApplyFixReport
    error = Signal(str)

    def __init__(self, iface: str, algo: Algorithm, parameters: dict,
                 score_before: float, diagnostic_id: Optional[str],
                 latency_before_ms: Optional[float] = None,
                 loss_before_pct: Optional[float] = None):
        super().__init__()
        self._iface = iface
        self._algo = algo
        self._parameters = parameters
        self._score_before = score_before
        self._diagnostic_id = diagnostic_id
        self._latency_before_ms = latency_before_ms
        self._loss_before_pct = loss_before_pct
        self._controller = get_controller()

    def _apply(self) -> ApplyResult:
        p = self._parameters
        if self._algo == Algorithm.LEAKY_BUCKET:
            return self._controller.apply_leaky_bucket(self._iface, p["rate_bps"], p["burst_bytes"])
        if self._algo == Algorithm.TOKEN_BUCKET:
            return self._controller.apply_token_bucket(self._iface, p["rate_bps"], p["burst_bytes"], p["latency_ms"])
        if self._algo == Algorithm.RED:
            return self._controller.apply_red(self._iface, p["min_th"], p["max_th"], p["max_p"], p["limit"])
        if self._algo == Algorithm.CODEL:
            return self._controller.apply_codel(self._iface, p["target_ms"], p["interval_ms"], p["limit"])
        return ApplyResult(success=False, message="Unknown algorithm.")

    def run(self):
        try:
            self.progress.emit("Saving current configuration for rollback...", 10)
            snapshot = self._controller.save_snapshot(self._iface)

            self.progress.emit(f"Applying {self._algo.value}...", 30)
            apply_result = self._apply()

            if not apply_result.success:
                self.complete.emit(ApplyFixReport(
                    applied=False,
                    policy_id=None,
                    apply_message=apply_result.message,
                    snapshot=snapshot,
                    score_before=self._score_before,
                    score_after=None,
                    verdict=None,
                    latency_before_ms=self._latency_before_ms,
                    loss_before_pct=self._loss_before_pct,
                ))
                return

            policy_id = str(uuid.uuid4())
            now = time.time()
            conn = get_connection()
            init_db(conn)
            repo = Repository(conn)
            repo.save_applied_policy(AppliedPolicy(
                id=policy_id,
                diagnostic_id=self._diagnostic_id,
                timestamp=now,
                interface=self._iface,
                algorithm=self._algo.value,
                parameters=json.dumps(self._parameters),
                snapshot_before=snapshot.raw,
                score_before=self._score_before,
            ))
            conn.close()

            self.progress.emit("Verifying improvement (re-measuring)...", 55)
            after_result, after_error = self._run_verification()

            if after_error or after_result is None:
                # Fix was applied and persisted, but we couldn't verify --
                # be honest about that rather than guessing an outcome.
                self.progress.emit("Applied, but verification failed.", 100)
                self.complete.emit(ApplyFixReport(
                    applied=True,
                    policy_id=policy_id,
                    apply_message=apply_result.message + " (Verification measurement failed: "
                                  + (after_error or "unknown error") + ")",
                    snapshot=snapshot,
                    score_before=self._score_before,
                    score_after=None,
                    verdict=None,
                    latency_before_ms=self._latency_before_ms,
                    loss_before_pct=self._loss_before_pct,
                ))
                return

            score_after = after_result.congestion_score.score
            verdict = verdict_for(self._score_before, score_after)

            latency_after = None
            loss_after = None
            if after_result.measurements:
                ms = after_result.measurements
                latency_after = sum(m.latency_ms for m in ms) / len(ms)
                loss_after = sum(m.packet_loss_pct for m in ms) / len(ms)

            conn = get_connection()
            init_db(conn)
            repo = Repository(conn)
            repo.save_applied_policy(AppliedPolicy(
                id=policy_id,
                diagnostic_id=self._diagnostic_id,
                timestamp=now,
                interface=self._iface,
                algorithm=self._algo.value,
                parameters=json.dumps(self._parameters),
                snapshot_before=snapshot.raw,
                score_before=self._score_before,
                score_after=score_after,
                verdict=verdict,
            ))
            conn.close()

            self.progress.emit("Complete!", 100)
            self.complete.emit(ApplyFixReport(
                applied=True,
                policy_id=policy_id,
                apply_message=apply_result.message,
                snapshot=snapshot,
                score_before=self._score_before,
                score_after=score_after,
                verdict=verdict,
                latency_before_ms=self._latency_before_ms,
                latency_after_ms=latency_after,
                loss_before_pct=self._loss_before_pct,
                loss_after_pct=loss_after,
                after_result=after_result,
            ))

        except Exception as e:
            self.error.emit(str(e))

    def _run_verification(self):
        """Runs DiagnosticsWorker's measurement logic synchronously in this
        thread (calling .run() directly, not .start()) so we don't need a
        nested Qt event loop just to wait for a result."""
        captured = {}
        verifier = DiagnosticsWorker(self._iface)
        verifier.complete.connect(lambda r: captured.__setitem__("result", r))
        verifier.error.connect(lambda e: captured.__setitem__("error", e))
        verifier.run()
        return captured.get("result"), captured.get("error")


class RollbackWorker(QThread):
    """Restores the pre-fix configuration for one applied policy and marks
    it as rolled back in the database."""

    progress = Signal(str, int)
    complete = Signal(object)   # ApplyResult
    error = Signal(str)

    def __init__(self, policy_id: str, snapshot: ConfigSnapshot):
        super().__init__()
        self._policy_id = policy_id
        self._snapshot = snapshot
        self._controller = get_controller()

    def run(self):
        try:
            self.progress.emit("Restoring previous configuration...", 30)
            result = self._controller.restore_snapshot(self._snapshot)

            if result.success:
                self.progress.emit("Recording rollback...", 80)
                conn = get_connection()
                init_db(conn)
                repo = Repository(conn)
                rows = repo.get_applied_policies(limit=200)
                row = next((r for r in rows if r["id"] == self._policy_id), None)
                if row:
                    repo.save_applied_policy(AppliedPolicy(
                        id=row["id"],
                        diagnostic_id=row["diagnostic_id"],
                        timestamp=row["timestamp"],
                        interface=row["interface"],
                        algorithm=row["algorithm"],
                        parameters=row["parameters"],
                        snapshot_before=row["snapshot_before"],
                        score_before=row["score_before"],
                        score_after=row["score_after"],
                        verdict=row["verdict"],
                        rolled_back_at=time.time(),
                    ))
                conn.close()

            self.progress.emit("Complete!", 100)
            self.complete.emit(result)
        except Exception as e:
            self.error.emit(str(e))