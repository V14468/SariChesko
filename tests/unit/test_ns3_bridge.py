"""Tests for sarichesko.simulation.ns3_bridge.

What is tested vs. what is NOT:
  TESTED:
    - Detection logic (find_ns3_executable / is_ns3_available) with
      monkeypatched shutil.which and os.environ.
    - "Not found" fallback path: Ns3SimulationEngine returns a clean,
      structured SimulationResult via PythonSimulationEngine with
      engine_used clearly indicating the fallback.
    - FlowMonitor XML parser: given mock XML shaped like real ns-3
      FlowMonitor output, the parser correctly populates SimulationResult
      metrics fields.
    - Subprocess error handling: timeout, non-zero exit, empty stdout.

  NOT TESTED (and why):
    - Actual end-to-end ns-3 subprocess execution — no ns-3 binary is
      available in this build/test environment, and we explicitly do NOT
      fabricate a fake one to pretend otherwise.
"""
import os
import textwrap

import pytest

from sarichesko.simulation.ns3_bridge import (
    find_ns3_executable,
    is_ns3_available,
    Ns3SimulationEngine,
    _parse_flowmonitor_xml,
    _parse_ns_value,
    _jain_fairness,
    _run_ns3_subprocess,
    _build_ns3_command,
)
from sarichesko.simulation.engine_base import (
    SimConfig,
    SimulationResult,
    SimMetrics,
    AlgorithmType,
)


# ===================================================================
# 1  Detection logic
# ===================================================================

class TestFindNs3Executable:
    """Test ns-3 detection via NS3_HOME, NS3_DIR, and PATH."""

    def test_not_found_when_nothing_set(self, monkeypatch, tmp_path):
        """With no env vars and no ns3 on PATH, returns None."""
        monkeypatch.delenv("NS3_HOME", raising=False)
        monkeypatch.delenv("NS3_DIR", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)
        assert find_ns3_executable() is None

    def test_found_via_ns3_home(self, monkeypatch, tmp_path):
        """NS3_HOME pointing at a directory with an ns3 executable is detected."""
        ns3_dir = tmp_path / "ns-3-dev"
        ns3_dir.mkdir()
        ns3_exe = ns3_dir / "ns3"
        ns3_exe.write_text("#!/bin/bash\n")
        monkeypatch.setenv("NS3_HOME", str(ns3_dir))
        monkeypatch.delenv("NS3_DIR", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)
        result = find_ns3_executable()
        assert result is not None
        assert "ns3" in result

    def test_found_via_ns3_dir_waf(self, monkeypatch, tmp_path):
        """NS3_DIR with legacy waf script is detected."""
        ns3_dir = tmp_path / "ns-3-old"
        ns3_dir.mkdir()
        waf = ns3_dir / "waf"
        waf.write_text("#!/usr/bin/env python\n")
        monkeypatch.delenv("NS3_HOME", raising=False)
        monkeypatch.setenv("NS3_DIR", str(ns3_dir))
        monkeypatch.setattr("shutil.which", lambda _: None)
        result = find_ns3_executable()
        assert result is not None
        assert "waf" in result

    def test_found_via_path(self, monkeypatch, tmp_path):
        """ns3 on PATH via shutil.which is detected."""
        monkeypatch.delenv("NS3_HOME", raising=False)
        monkeypatch.delenv("NS3_DIR", raising=False)
        fake_path = str(tmp_path / "ns3")
        monkeypatch.setattr("shutil.which", lambda name: fake_path if name == "ns3" else None)
        result = find_ns3_executable()
        assert result == fake_path

    def test_ns3_home_takes_precedence_over_path(self, monkeypatch, tmp_path):
        """NS3_HOME is checked before PATH."""
        ns3_dir = tmp_path / "ns-3-dev"
        ns3_dir.mkdir()
        ns3_exe = ns3_dir / "ns3"
        ns3_exe.write_text("#!/bin/bash\n")
        monkeypatch.setenv("NS3_HOME", str(ns3_dir))
        monkeypatch.delenv("NS3_DIR", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/ns3")
        result = find_ns3_executable()
        # Should find the NS3_HOME one, not the PATH one
        assert str(ns3_dir) in result

    def test_env_var_pointing_to_nonexistent_dir(self, monkeypatch, tmp_path):
        """NS3_HOME pointing at a nonexistent directory is ignored."""
        monkeypatch.setenv("NS3_HOME", str(tmp_path / "does-not-exist"))
        monkeypatch.delenv("NS3_DIR", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)
        assert find_ns3_executable() is None

    def test_env_var_dir_without_executable(self, monkeypatch, tmp_path):
        """NS3_HOME pointing at a real directory without ns3/waf is ignored."""
        empty_dir = tmp_path / "empty-ns3"
        empty_dir.mkdir()
        monkeypatch.setenv("NS3_HOME", str(empty_dir))
        monkeypatch.delenv("NS3_DIR", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)
        assert find_ns3_executable() is None


class TestIsNs3Available:
    """Thin wrapper around find_ns3_executable — test the boolean."""

    def test_false_when_not_found(self, monkeypatch):
        monkeypatch.delenv("NS3_HOME", raising=False)
        monkeypatch.delenv("NS3_DIR", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)
        assert is_ns3_available() is False

    def test_true_when_found(self, monkeypatch, tmp_path):
        ns3_dir = tmp_path / "ns3-root"
        ns3_dir.mkdir()
        (ns3_dir / "ns3").write_text("#!/bin/bash\n")
        monkeypatch.setenv("NS3_HOME", str(ns3_dir))
        monkeypatch.delenv("NS3_DIR", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)
        assert is_ns3_available() is True


# ===================================================================
# 2  Fallback path — "ns-3 not available"
# ===================================================================

class TestNs3EngineFallback:
    """When ns-3 is not detected, Ns3SimulationEngine must fall back to
    PythonSimulationEngine without crashing and honestly label engine_used."""

    @pytest.fixture(autouse=True)
    def _no_ns3(self, monkeypatch):
        monkeypatch.delenv("NS3_HOME", raising=False)
        monkeypatch.delenv("NS3_DIR", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)

    def _make_config(self, algo=AlgorithmType.CODEL):
        return SimConfig(
            scenario="bulk_transfer",
            algorithm=algo,
            duration_s=1.0,
            link_bandwidth_mbps=10.0,
            queue_size=50,
        )

    def test_ns3_available_reports_false(self):
        engine = Ns3SimulationEngine()
        assert engine.ns3_available is False

    def test_returns_simulation_result(self):
        engine = Ns3SimulationEngine()
        result = engine.run(self._make_config())
        assert isinstance(result, SimulationResult)

    def test_engine_used_labels_fallback(self):
        engine = Ns3SimulationEngine()
        result = engine.run(self._make_config())
        assert "python_fallback" in result.engine_used
        assert "ns-3 unavailable" in result.engine_used

    def test_metrics_are_populated(self):
        engine = Ns3SimulationEngine()
        result = engine.run(self._make_config())
        assert isinstance(result.metrics, SimMetrics)
        assert result.metrics.total_packets > 0

    def test_config_preserved(self):
        config = self._make_config(AlgorithmType.RED)
        engine = Ns3SimulationEngine()
        result = engine.run(config)
        assert result.scenario == "bulk_transfer"
        assert result.algorithm == "RED"
        assert result.config is config

    def test_all_algorithms_produce_results(self):
        """Every AlgorithmType runs cleanly through the fallback path."""
        engine = Ns3SimulationEngine()
        for algo in AlgorithmType:
            result = engine.run(self._make_config(algo))
            assert isinstance(result, SimulationResult)
            assert result.algorithm == algo.value


# ===================================================================
# 3  FlowMonitor XML parser
# ===================================================================

SAMPLE_FLOWMON_XML = textwrap.dedent("""\
    <?xml version="1.0"?>
    <FlowMonitor>
      <FlowStats>
        <Flow flowId="1"
              txPackets="1000" rxPackets="950" lostPackets="50"
              txBytes="1500000" rxBytes="1425000"
              delaySum="950000000ns" jitterSum="100000000ns" />
        <Flow flowId="2"
              txPackets="800" rxPackets="790" lostPackets="10"
              txBytes="1200000" rxBytes="1185000"
              delaySum="395000000ns" jitterSum="50000000ns" />
      </FlowStats>
    </FlowMonitor>
""")


class TestFlowMonitorParser:
    """Tests the FlowMonitor XML parser with mock XML data.

    NOTE: This tests the PARSER logic, NOT an actual integration with a real
    ns-3 installation. The XML is hand-crafted to match the FlowMonitor
    output format documented in ns-3 source.
    """

    def _config(self):
        return SimConfig(
            scenario="bulk_transfer",
            algorithm=AlgorithmType.RED,
            duration_s=10.0,
            link_bandwidth_mbps=10.0,
            queue_size=100,
        )

    def test_returns_simulation_result(self):
        result = _parse_flowmonitor_xml(SAMPLE_FLOWMON_XML, self._config())
        assert isinstance(result, SimulationResult)

    def test_engine_used_is_ns3(self):
        result = _parse_flowmonitor_xml(SAMPLE_FLOWMON_XML, self._config())
        assert result.engine_used == "ns3"

    def test_total_packets(self):
        result = _parse_flowmonitor_xml(SAMPLE_FLOWMON_XML, self._config())
        assert result.metrics.total_packets == 1800  # 1000 + 800

    def test_delivered_packets(self):
        result = _parse_flowmonitor_xml(SAMPLE_FLOWMON_XML, self._config())
        assert result.metrics.delivered_packets == 1740  # 950 + 790

    def test_dropped_packets(self):
        result = _parse_flowmonitor_xml(SAMPLE_FLOWMON_XML, self._config())
        assert result.metrics.dropped_packets == 60  # 50 + 10

    def test_loss_percentage(self):
        result = _parse_flowmonitor_xml(SAMPLE_FLOWMON_XML, self._config())
        expected_loss = (60 / 1800) * 100
        assert abs(result.metrics.loss_pct - expected_loss) < 0.01

    def test_throughput_calculation(self):
        result = _parse_flowmonitor_xml(SAMPLE_FLOWMON_XML, self._config())
        # rxBytes=2610000, duration=10s => (2610000*8)/(10*1e6) = 2.088 Mbps
        expected = (2_610_000 * 8) / (10.0 * 1_000_000)
        assert abs(result.metrics.throughput_mbps - expected) < 0.01

    def test_avg_latency_calculation(self):
        result = _parse_flowmonitor_xml(SAMPLE_FLOWMON_XML, self._config())
        # Total delay: 950000000 + 395000000 = 1345000000 ns
        # Total rx: 1740 packets
        # Avg: 1345000000 / 1740 / 1e6 ms
        expected_ms = (950_000_000 + 395_000_000) / 1740 / 1_000_000
        assert abs(result.metrics.avg_latency_ms - expected_ms) < 0.01

    def test_fairness_index(self):
        result = _parse_flowmonitor_xml(SAMPLE_FLOWMON_XML, self._config())
        # per_flow_rx = [950, 790] => Jain's fairness
        # sum = 1740, sum_sq = 950^2 + 790^2 = 902500 + 624100 = 1526600
        # J = 1740^2 / (2 * 1526600) = 3027600 / 3053200 ≈ 0.9916
        assert result.metrics.fairness_index > 0.99
        assert result.metrics.fairness_index <= 1.0

    def test_scenario_and_algorithm_preserved(self):
        result = _parse_flowmonitor_xml(SAMPLE_FLOWMON_XML, self._config())
        assert result.scenario == "bulk_transfer"
        assert result.algorithm == "RED"

    def test_empty_flowstats(self):
        """Empty FlowStats should produce zero metrics, not crash."""
        xml = "<FlowMonitor><FlowStats></FlowStats></FlowMonitor>"
        result = _parse_flowmonitor_xml(xml, self._config())
        assert result.metrics.total_packets == 0
        assert result.metrics.throughput_mbps == 0.0
        assert result.metrics.loss_pct == 0.0
        assert result.metrics.fairness_index == 1.0


# ===================================================================
# 4  Time string parser
# ===================================================================

class TestParseNsValue:

    def test_nanoseconds(self):
        assert _parse_ns_value("12345ns") == 12345.0

    def test_microseconds(self):
        assert _parse_ns_value("500us") == 500_000.0

    def test_milliseconds(self):
        assert _parse_ns_value("10ms") == 10_000_000.0

    def test_seconds(self):
        assert _parse_ns_value("1s") == 1_000_000_000.0

    def test_with_plus_prefix(self):
        assert _parse_ns_value("+12345ns") == 12345.0

    def test_bare_number(self):
        assert _parse_ns_value("999") == 999.0

    def test_garbage_returns_zero(self):
        assert _parse_ns_value("not-a-number") == 0.0


# ===================================================================
# 5  Jain's fairness index
# ===================================================================

class TestJainFairness:

    def test_single_flow(self):
        assert _jain_fairness([100]) == 1.0

    def test_empty(self):
        assert _jain_fairness([]) == 1.0

    def test_equal_flows(self):
        assert abs(_jain_fairness([100, 100, 100]) - 1.0) < 0.001

    def test_unequal_flows(self):
        # [1000, 0] => J = 1000^2 / (2 * 1000^2) = 0.5
        assert abs(_jain_fairness([1000, 0]) - 0.5) < 0.001

    def test_all_zeros(self):
        assert _jain_fairness([0, 0, 0]) == 1.0


# ===================================================================
# 6  Subprocess error handling (mocked)
# ===================================================================

class TestSubprocessErrorHandling:
    """Test that subprocess failures produce RuntimeError, not silent corruption."""

    def _config(self):
        return SimConfig(
            scenario="bursty_traffic",
            algorithm=AlgorithmType.CODEL,
            duration_s=5.0,
        )

    def test_nonzero_exit_raises(self, monkeypatch):
        import subprocess as sp
        fake_result = sp.CompletedProcess(args=[], returncode=1, stdout="", stderr="Segfault")
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_result)
        with pytest.raises(RuntimeError, match="exited with code 1"):
            _run_ns3_subprocess("/fake/ns3", self._config())

    def test_empty_stdout_raises(self, monkeypatch):
        import subprocess as sp
        fake_result = sp.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_result)
        with pytest.raises(RuntimeError, match="no stdout output"):
            _run_ns3_subprocess("/fake/ns3", self._config())

    def test_timeout_raises(self, monkeypatch):
        import subprocess as sp
        def fake_run(*a, **kw):
            raise sp.TimeoutExpired(cmd="ns3", timeout=120)
        monkeypatch.setattr("subprocess.run", fake_run)
        with pytest.raises(RuntimeError, match="timed out"):
            _run_ns3_subprocess("/fake/ns3", self._config())

    def test_file_not_found_raises(self, monkeypatch):
        def fake_run(*a, **kw):
            raise FileNotFoundError("No such file")
        monkeypatch.setattr("subprocess.run", fake_run)
        with pytest.raises(RuntimeError, match="not found"):
            _run_ns3_subprocess("/fake/ns3", self._config())

    def test_invalid_xml_raises(self, monkeypatch):
        import subprocess as sp
        fake_result = sp.CompletedProcess(args=[], returncode=0, stdout="NOT XML AT ALL", stderr="")
        monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_result)
        with pytest.raises(RuntimeError, match="parse.*XML"):
            _run_ns3_subprocess("/fake/ns3", self._config())


# ===================================================================
# 7  ns-3 error fallback in Ns3SimulationEngine.run()
# ===================================================================

class TestNs3EngineSubprocessFallback:
    """When ns-3 IS detected but the subprocess fails, the engine should
    fall back to PythonSimulationEngine with an error-descriptive engine_used."""

    def test_fallback_on_subprocess_error(self, monkeypatch, tmp_path):
        # Set up so ns-3 IS "detected"
        ns3_dir = tmp_path / "ns3"
        ns3_dir.mkdir()
        (ns3_dir / "ns3").write_text("#!/bin/bash\n")
        monkeypatch.setenv("NS3_HOME", str(ns3_dir))
        monkeypatch.delenv("NS3_DIR", raising=False)
        monkeypatch.setattr("shutil.which", lambda _: None)

        # But make subprocess.run raise
        def fake_run(*a, **kw):
            raise FileNotFoundError("ns3 binary gone")
        monkeypatch.setattr("subprocess.run", fake_run)

        engine = Ns3SimulationEngine()
        assert engine.ns3_available is True

        config = SimConfig(
            scenario="mixed_traffic",
            algorithm=AlgorithmType.LEAKY_BUCKET,
            duration_s=1.0,
        )
        result = engine.run(config)

        # Should NOT crash — should fall back
        assert isinstance(result, SimulationResult)
        assert "python_fallback" in result.engine_used
        assert "ns-3 error" in result.engine_used
        assert result.metrics.total_packets > 0


# ===================================================================
# 8  Command builder
# ===================================================================

class TestBuildNs3Command:

    def test_command_contains_scenario(self):
        config = SimConfig(scenario="bulk_transfer", algorithm=AlgorithmType.RED)
        cmd = _build_ns3_command("/usr/local/ns3/ns3", config)
        assert any("--scenario=bulk_transfer" in arg for arg in cmd)

    def test_command_contains_qdisc(self):
        config = SimConfig(scenario="bulk_transfer", algorithm=AlgorithmType.CODEL)
        cmd = _build_ns3_command("/usr/local/ns3/ns3", config)
        assert any("CoDelQueueDisc" in arg for arg in cmd)

    def test_command_starts_with_executable(self):
        config = SimConfig(scenario="bulk_transfer", algorithm=AlgorithmType.RED)
        cmd = _build_ns3_command("/my/ns3", config)
        assert cmd[0] == "/my/ns3"
