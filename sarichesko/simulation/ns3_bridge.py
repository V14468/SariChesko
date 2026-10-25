"""ns-3 subprocess bridge for SariChesko simulation engine.

Detects whether a real ns-3 installation is available on this machine,
and either:
  a) Runs a simulation scenario as an ns-3 subprocess, parses its
     FlowMonitor XML output, and returns a SimulationResult, or
  b) Returns a structured "not available" signal and falls back to the
     pure-Python PythonSimulationEngine — honestly labelling which
     engine actually ran.

Detection strategy:
  1. Check NS3_HOME or NS3_DIR environment variable for a directory
     containing a runnable `ns3` executable or `waf` script.
  2. Check if `ns3` is on the system PATH via shutil.which().

This module adds NO new dependencies — it uses only the Python stdlib
and project-internal imports.
"""

import logging
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .engine_base import (
    SimulationEngineBase,
    SimConfig,
    SimulationResult,
    SimMetrics,
    PacketEvent,
)
from .python_sim import PythonSimulationEngine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ns-3 detection
# ---------------------------------------------------------------------------

def find_ns3_executable() -> str | None:
    """Return the absolute path to a usable ns-3 launcher, or None.

    Checks, in order:
      1. $NS3_HOME/ns3  (or $NS3_HOME/waf for older ns-3 builds)
      2. $NS3_DIR/ns3   (or $NS3_DIR/waf)
      3. `ns3` on PATH   (shutil.which)
    """
    for env_var in ("NS3_HOME", "NS3_DIR"):
        ns3_dir = os.environ.get(env_var)
        if not ns3_dir:
            continue
        ns3_dir = Path(ns3_dir)
        if not ns3_dir.is_dir():
            logger.debug("$%s=%s is not a directory, skipping", env_var, ns3_dir)
            continue
        # Prefer the modern `ns3` launcher over legacy `waf`.
        for candidate in ("ns3", "ns3.exe", "waf", "waf.bat"):
            exe = ns3_dir / candidate
            if exe.is_file():
                logger.info("Found ns-3 via $%s: %s", env_var, exe)
                return str(exe)

    which_result = shutil.which("ns3")
    if which_result:
        logger.info("Found ns-3 on PATH: %s", which_result)
        return which_result

    logger.debug("ns-3 not found (checked NS3_HOME, NS3_DIR, PATH)")
    return None


def is_ns3_available() -> bool:
    """Quick boolean check: is a usable ns-3 installation detected?"""
    return find_ns3_executable() is not None


# ---------------------------------------------------------------------------
# ns-3 readiness status (used by the engine selector UI)
# ---------------------------------------------------------------------------

from dataclasses import dataclass as _dataclass   # noqa: E402  (late import to keep top clean)
import sys as _sys                                  # noqa: E402


@_dataclass
class Ns3Status:
    """Structured readiness report for the ns-3 backend.

    state:
      "unavailable"       – no ns-3 launcher found at all
      "scenario_missing"  – launcher found, but sarichesko-sim.cc is absent
      "ready"             – launcher + scenario program both present
    message:
      Human-readable explanation of what to do next.
    launcher:
      Absolute path to the ns-3 launcher, or None.
    root:
      ns-3 root directory (parent of launcher), or None.
    """
    state: str           # "unavailable" | "scenario_missing" | "ready"
    message: str
    launcher: str | None = None
    root: Path | None = None


def ns3_status() -> Ns3Status:
    """Probe the system and return the current ns-3 readiness status.

    On Windows (not WSL), ns-3 is effectively unavailable because ns-3
    does not build natively on Windows.  The UI should say so plainly.
    """
    # Windows check — ns-3 doesn't run natively on Windows
    if _sys.platform == "win32" and "microsoft" not in (
        os.environ.get("WSL_DISTRO_NAME", "")
        + os.environ.get("WSLENV", "")
    ).lower():
        exe = find_ns3_executable()
        if exe is None:
            return Ns3Status(
                state="unavailable",
                message=(
                    "ns-3 is not available on Windows. "
                    "It runs on Linux or WSL. The built-in Python engine "
                    "is used instead."
                ),
            )
        # If somehow an ns3 launcher exists on Windows (e.g. WSL path
        # leaked), continue with the normal checks below.

    exe = find_ns3_executable()
    if exe is None:
        return Ns3Status(
            state="unavailable",
            message=(
                "No ns-3 installation found. Set NS3_HOME or NS3_DIR to "
                "your ns-3 directory, or add ns3 to PATH. "
                "The built-in Python engine is used instead."
            ),
        )

    root = _ns3_root_from_launcher(exe)
    scratch_src = root / "scratch" / "sarichesko-sim.cc"

    if not scratch_src.is_file():
        return Ns3Status(
            state="scenario_missing",
            message=(
                f"ns-3 found at {root}, but the SariChesko scenario program "
                f"is missing. Copy sarichesko-sim.cc into {root / 'scratch'}/.  "
                "NOTE: This C++ source does not exist in the SariChesko "
                "repository yet — it has not been authored and verified "
                "against a real ns-3 build."
            ),
            launcher=exe,
            root=root,
        )

    return Ns3Status(
        state="ready",
        message=f"ns-3 ready at {root} with sarichesko-sim scenario.",
        launcher=exe,
        root=root,
    )


# ---------------------------------------------------------------------------
# FlowMonitor XML output parser
# ---------------------------------------------------------------------------

_NS_FLOWMON = "http://www.nsnam.org/FlowMonitor"


def _parse_flowmonitor_xml(xml_text: str, config: SimConfig) -> SimulationResult:
    """Parse ns-3 FlowMonitor XML output into a SimulationResult.

    Expected XML structure (ns-3 FlowMonitor standard output):

        <FlowMonitor>
          <FlowStats>
            <Flow flowId="1" ... txPackets="N" rxPackets="N"
                  lostPackets="N" delaySum="XXns" jitterSum="XXns"
                  txBytes="N" rxBytes="N" ... />
            ...
          </FlowStats>
        </FlowMonitor>

    This parser aggregates across all flows to produce summary metrics.
    """
    root = ET.fromstring(xml_text)

    # FlowMonitor XML may or may not use a namespace.
    flow_stats_el = root.find("FlowStats")
    if flow_stats_el is None:
        flow_stats_el = root.find(f"{{{_NS_FLOWMON}}}FlowStats")

    flows = []
    if flow_stats_el is not None:
        flows = list(flow_stats_el.findall("Flow"))
        if not flows:
            flows = list(flow_stats_el.findall(f"{{{_NS_FLOWMON}}}Flow"))

    total_tx_packets = 0
    total_rx_packets = 0
    total_lost_packets = 0
    total_rx_bytes = 0
    total_delay_ns = 0
    max_delay_ns = 0
    per_flow_rx = []

    for flow in flows:
        tx = int(flow.get("txPackets", "0"))
        rx = int(flow.get("rxPackets", "0"))
        lost = int(flow.get("lostPackets", "0"))
        rx_bytes = int(flow.get("rxBytes", "0"))

        delay_sum_str = flow.get("delaySum", "0ns")
        delay_ns = _parse_ns_value(delay_sum_str)

        total_tx_packets += tx
        total_rx_packets += rx
        total_lost_packets += lost
        total_rx_bytes += rx_bytes
        total_delay_ns += delay_ns
        per_flow_rx.append(rx)

        if rx > 0:
            avg_delay_this_flow = delay_ns / rx
            max_delay_ns = max(max_delay_ns, avg_delay_this_flow)

    # Compute aggregate metrics
    duration = config.duration_s if config.duration_s > 0 else 1.0

    throughput_mbps = (total_rx_bytes * 8) / (duration * 1_000_000) if duration > 0 else 0.0

    avg_latency_ms = 0.0
    if total_rx_packets > 0:
        avg_latency_ms = (total_delay_ns / total_rx_packets) / 1_000_000  # ns -> ms

    max_latency_ms = max_delay_ns / 1_000_000  # ns -> ms

    loss_pct = 0.0
    if total_tx_packets > 0:
        loss_pct = (total_lost_packets / total_tx_packets) * 100

    fairness_index = _jain_fairness(per_flow_rx)

    metrics = SimMetrics(
        throughput_mbps=throughput_mbps,
        avg_latency_ms=avg_latency_ms,
        max_latency_ms=max_latency_ms,
        loss_pct=loss_pct,
        avg_queue_depth=0.0,   # FlowMonitor doesn't directly expose queue depth
        max_queue_depth=0,
        fairness_index=fairness_index,
        total_packets=total_tx_packets,
        dropped_packets=total_lost_packets,
        delivered_packets=total_rx_packets,
    )

    return SimulationResult(
        scenario=config.scenario,
        algorithm=config.algorithm.value,
        config=config,
        duration_s=config.duration_s,
        metrics=metrics,
        events=[],                    # FlowMonitor doesn't provide per-packet events
        queue_depth_over_time=[],
        latency_over_time=[],
        engine_used="ns3",
    )


def _parse_ns_value(value_str: str) -> float:
    """Parse an ns-3 time string like '12345ns' or '+12345.0ns' to float nanoseconds."""
    s = value_str.strip().lstrip("+")
    if s.endswith("ns"):
        return float(s[:-2])
    if s.endswith("us"):
        return float(s[:-2]) * 1_000
    if s.endswith("ms"):
        return float(s[:-2]) * 1_000_000
    if s.endswith("s"):
        return float(s[:-1]) * 1_000_000_000
    try:
        return float(s)
    except ValueError:
        return 0.0


def _jain_fairness(shares: list[int]) -> float:
    """Compute Jain's fairness index across per-flow delivered packet counts."""
    if len(shares) <= 1:
        return 1.0
    total = sum(shares)
    if total == 0:
        return 1.0
    sum_sq = sum(x * x for x in shares)
    return (total ** 2) / (len(shares) * sum_sq)


# ---------------------------------------------------------------------------
# ns-3 subprocess runner
# ---------------------------------------------------------------------------

_ALGO_TO_NS3_QDISC = {
    "Leaky Bucket": "ns3::TbfQueueDisc",    # ns-3's TBF with minimal burst
    "Token Bucket": "ns3::TbfQueueDisc",
    "RED": "ns3::RedQueueDisc",
    "CoDel": "ns3::CoDelQueueDisc",
}

# Timeout for ns-3 subprocess execution (seconds).
# 600 s is intentionally generous: the first invocation of a scratch program
# triggers a full ns-3 build (CMake configure + compile), which can take
# several minutes on modest hardware.  Subsequent runs reuse the cache and
# complete in seconds.
_NS3_SUBPROCESS_TIMEOUT = 600


def _build_ns3_command(ns3_exe: str, config: SimConfig, out_path: str = "") -> list[str]:
    """Build the command line for running an ns-3 simulation.

    The ns-3 program is ``sarichesko-sim``, expected at
    ``<ns3 root>/scratch/sarichesko-sim.cc``.  It is invoked as::

        <launcher> run "sarichesko-sim --scenario=.. --qdisc=.. ...
                        --out=<absolute temp file>"

    For legacy waf builds the invocation is::

        waf --run "sarichesko-sim --scenario=.. ..."

    The program writes FlowMonitor XML to the ``--out`` file.  The bridge
    reads **that file** instead of parsing stdout (ns-3 build output pollutes
    stdout) and always deletes the temp file.

    NOTE: The ``sarichesko-sim`` program does NOT ship with SariChesko.
    It must be authored as an ns-3 C++ scratch program and placed in the
    user's ns-3 installation.  The command syntax here may be adjusted
    after testing against a real ns-3 build.
    """
    qdisc = _ALGO_TO_NS3_QDISC.get(config.algorithm.value, "ns3::CoDelQueueDisc")

    # Build the program argument string (everything after the program name)
    prog_args = (
        f"sarichesko-sim"
        f" --scenario={config.scenario}"
        f" --qdisc={qdisc}"
        f" --duration={config.duration_s}"
        f" --linkBw={config.link_bandwidth_mbps}Mbps"
        f" --linkDelay={config.link_delay_ms}ms"
        f" --queueSize={config.queue_size}"
        f" --numFlows={config.num_flows}"
        f" --out={out_path}"
    )

    launcher_name = Path(ns3_exe).name.lower()
    if launcher_name.startswith("waf"):
        # Legacy waf: waf --run "program --args"
        cmd = [ns3_exe, "--run", prog_args]
    else:
        # Modern ns3 launcher: ns3 run "program --args"
        cmd = [ns3_exe, "run", prog_args]
    return cmd


def _ns3_root_from_launcher(ns3_exe: str) -> Path:
    """Derive the ns-3 root directory from the launcher path."""
    return Path(ns3_exe).resolve().parent


def _run_ns3_subprocess(ns3_exe: str, config: SimConfig) -> SimulationResult:
    """Execute ns-3 as a subprocess and parse its FlowMonitor XML output.

    The program writes FlowMonitor XML to a temp file specified via ``--out``.
    We read that file (not stdout, which ns-3 build noise pollutes) and
    always delete the temp file afterwards.
    """
    # Create a temp file for FlowMonitor XML output
    fd, out_path = tempfile.mkstemp(suffix=".xml", prefix="sarichesko_ns3_")
    os.close(fd)  # Close immediately; ns-3 will write to it

    cmd = _build_ns3_command(ns3_exe, config, out_path)
    cwd = str(_ns3_root_from_launcher(ns3_exe))
    logger.info("Running ns-3: %s  (cwd=%s, out=%s)", " ".join(cmd), cwd, out_path)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_NS3_SUBPROCESS_TIMEOUT,
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        _cleanup_temp(out_path)
        raise RuntimeError(
            f"ns-3 subprocess timed out after {_NS3_SUBPROCESS_TIMEOUT}s. "
            f"Command: {' '.join(cmd)}"
        )
    except FileNotFoundError:
        _cleanup_temp(out_path)
        raise RuntimeError(
            f"ns-3 executable not found at '{ns3_exe}'. "
            f"Check your NS3_HOME / NS3_DIR environment variable or PATH."
        )
    except OSError as e:
        _cleanup_temp(out_path)
        raise RuntimeError(
            f"Failed to launch ns-3 subprocess: {e}. "
            f"Command: {' '.join(cmd)}"
        )

    if result.returncode != 0:
        _cleanup_temp(out_path)
        stderr_snippet = (result.stderr or "").strip()[:500]
        raise RuntimeError(
            f"ns-3 exited with code {result.returncode}. "
            f"stderr: {stderr_snippet}"
        )

    # Read FlowMonitor XML from the output file (NOT from stdout)
    try:
        xml_output = Path(out_path).read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise RuntimeError(
            "ns-3 completed but did not write the expected output file. "
            f"Expected: {out_path}"
        )
    finally:
        _cleanup_temp(out_path)

    if not xml_output:
        raise RuntimeError(
            "ns-3 output file was empty. Expected FlowMonitor XML. "
            f"stderr: {(result.stderr or '').strip()[:300]}"
        )

    try:
        return _parse_flowmonitor_xml(xml_output, config)
    except ET.ParseError as e:
        raise RuntimeError(
            f"Failed to parse ns-3 FlowMonitor XML output: {e}. "
            f"First 200 chars: {xml_output[:200]}"
        )


def _cleanup_temp(path: str) -> None:
    """Silently remove a temp file."""
    try:
        os.unlink(path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Public simulation engine
# ---------------------------------------------------------------------------

class Ns3SimulationEngine(SimulationEngineBase):
    """Simulation engine that attempts to use a real ns-3 installation.

    If ns-3 is detected, runs the simulation as an ns-3 subprocess and
    parses FlowMonitor XML output into a SimulationResult.

    If ns-3 is NOT detected, transparently falls back to the pure-Python
    PythonSimulationEngine and sets engine_used to clearly indicate
    which engine actually ran and why.
    """

    def __init__(self):
        self._ns3_exe = find_ns3_executable()
        self._fallback = PythonSimulationEngine()

    @property
    def ns3_available(self) -> bool:
        """Whether a real ns-3 installation was detected."""
        return self._ns3_exe is not None

    def run(self, config: SimConfig) -> SimulationResult:
        """Run a simulation, using ns-3 if available, otherwise Python fallback.

        The returned SimulationResult.engine_used always honestly reports
        which engine actually executed the simulation.
        """
        if not self._ns3_exe:
            logger.info(
                "ns-3 not available; falling back to PythonSimulationEngine"
            )
            result = self._fallback.run(config)
            result.engine_used = "python_fallback (ns-3 unavailable)"
            return result

        try:
            return _run_ns3_subprocess(self._ns3_exe, config)
        except RuntimeError as e:
            logger.warning("ns-3 subprocess failed: %s — falling back to Python engine", e)
            result = self._fallback.run(config)
            result.engine_used = f"python_fallback (ns-3 error: {str(e)[:100]})"
            return result
