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
_NS3_SUBPROCESS_TIMEOUT = 120


def _build_ns3_command(ns3_exe: str, config: SimConfig) -> list[str]:
    """Build the command line for running an ns-3 simulation.

    This targets a hypothetical ns-3 scratch script 'sarichesko-sim' that
    accepts command-line arguments matching our SimConfig fields and writes
    FlowMonitor XML to stdout.

    NOTE: This exact script does not ship with SariChesko — it would need to
    be authored as an ns-3 C++ scratch program in the user's ns-3 installation.
    """
    qdisc = _ALGO_TO_NS3_QDISC.get(config.algorithm.value, "ns3::CoDelQueueDisc")
    cmd = [
        ns3_exe, "run", "sarichesko-sim", "--",
        f"--scenario={config.scenario}",
        f"--qdisc={qdisc}",
        f"--duration={config.duration_s}",
        f"--linkBw={config.link_bandwidth_mbps}Mbps",
        f"--linkDelay={config.link_delay_ms}ms",
        f"--queueSize={config.queue_size}",
        f"--numFlows={config.num_flows}",
    ]
    return cmd


def _run_ns3_subprocess(ns3_exe: str, config: SimConfig) -> SimulationResult:
    """Execute ns-3 as a subprocess and parse its FlowMonitor XML output.

    Follows the same subprocess conventions as the platform controllers:
    capture_output=True, text=True, explicit timeout, structured error messages.
    """
    cmd = _build_ns3_command(ns3_exe, config)
    logger.info("Running ns-3: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_NS3_SUBPROCESS_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"ns-3 subprocess timed out after {_NS3_SUBPROCESS_TIMEOUT}s. "
            f"Command: {' '.join(cmd)}"
        )
    except FileNotFoundError:
        raise RuntimeError(
            f"ns-3 executable not found at '{ns3_exe}'. "
            f"Check your NS3_HOME / NS3_DIR environment variable or PATH."
        )
    except OSError as e:
        raise RuntimeError(
            f"Failed to launch ns-3 subprocess: {e}. "
            f"Command: {' '.join(cmd)}"
        )

    if result.returncode != 0:
        stderr_snippet = (result.stderr or "").strip()[:500]
        raise RuntimeError(
            f"ns-3 exited with code {result.returncode}. "
            f"stderr: {stderr_snippet}"
        )

    xml_output = result.stdout.strip()
    if not xml_output:
        raise RuntimeError(
            "ns-3 produced no stdout output. Expected FlowMonitor XML. "
            f"stderr: {(result.stderr or '').strip()[:300]}"
        )

    try:
        return _parse_flowmonitor_xml(xml_output, config)
    except ET.ParseError as e:
        raise RuntimeError(
            f"Failed to parse ns-3 FlowMonitor XML output: {e}. "
            f"First 200 chars of stdout: {xml_output[:200]}"
        )


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
