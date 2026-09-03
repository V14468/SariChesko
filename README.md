# SariChesko

> **Etymology:** Derived from the Telugu phrase *సరిచేస్కో (Sari-chesko)*, signifying *"To resolve, rectify, or sort out."*

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=flat-square&logo=python)](https://www.python.org/)
[![Framework](https://img.shields.io/badge/GUI-PySide6%20%2F%20Qt6-green.svg?style=flat-square&logo=qt)](https://www.qt.io/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20Linux-lightgrey.svg?style=flat-square)](https://github.com/)
[![Simulation](https://img.shields.io/badge/Simulation-ns--3%20%7C%20Python%20DES-orange.svg?style=flat-square)](https://www.nsnam.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](LICENSE)

An open-source, cross-platform research and desktop utility engineered for **real-time network congestion detection, multi-hop fault attribution, and automated traffic mitigation**. Developed as an academic Computer Networks Project-Based Learning (PBL) initiative, SariChesko bridges empirical transport-layer telemetry with classical traffic shaping and Active Queue Management (AQM) algorithms.

---

## Abstract & System Overview

Network degradation frequently suffers from ambiguous fault localization: end users cannot readily distinguish between local host bufferbloat, local area network (LAN) saturation, last-mile physical link degradation, and upstream transit provider outages. Consequently, applying host-level traffic control indiscriminately can be futile or counterproductive.

**SariChesko** addresses this challenge through a closed-loop diagnostic and mitigation pipeline:
1. **Telemetry & Baselines:** Continuously samples physical interface metrics and establishes dynamic empirical baselines.
2. **Multi-Target Fault Attribution:** Dispatches sequential probes across the network hierarchy (loopback $\to$ LAN gateway $\to$ ISP edge $\to$ transit WAN $\to$ DNS $\to$ CDN) to classify whether bottlenecks are edge-local or upstream.
3. **Deterministic Heuristic Selection:** Recommends optimal algorithmic remedies (Leaky Bucket, Token Bucket, RED, or CoDel) based on observable queue characteristics.
4. **Human-in-the-Loop Safe Actuation:** Executes operating-system-level traffic control (via Linux `iproute2`/`tc` or Windows QoS/WTC) exclusively upon explicit user authorization.
5. **Empirical Verification & Automatic Rollback:** Measures post-intervention link performance against pre-intervention state, offering deterministic one-click rollback if link quality fails to improve.

flowchart LR
    A[Monitor Telemetry] --> B[Detect Congestion]
    B --> C[Attribution Probing]
    C --> D[Explain Diagnosis]
    D --> E[Recommend Algorithm]
    E --> F[User Authorization]
    F --> G[Actuate Policy]
    G --> H{Verify Metric Gain}
    H -- Improved --> I[Persist Configuration]
    H -- Stagnant / Degraded --> J[Rollback Snapshot]


---

## Dual Operational Paradigms

To support both live system management and safe academic exploration, SariChesko provides two decoupled operational modes:

### Paradigm A: Live Production Network Telemetry
* **Interface Auto-Discovery:** Enumerates network interfaces via platform-native socket APIs and `psutil`.
* **Dynamic Baselining:** Derives statistically normalized baselines for latency, throughput, and packet-drop rates under resting conditions versus loaded states.
* **Anomaly Detection:** Flags deviations from established statistical baselines using composite scoring.
* **Kernel-Level Policy Enforcement:** Modifies queuing disciplines (`qdisc`) on Linux or Traffic Control / Policy QoS filters on Windows.
* **Snapshot & Verification:** Enforces a 30-second empirical post-actuation validation cycle with automated state recovery upon regression.

### Paradigm B: Discrete-Event Simulation Laboratory
* **Controlled Evaluation Sandbox:** Provides an isolated testbed to analyze algorithm dynamics without destabilizing host networking.
* **Dual-Engine Architecture:** Backed by **ns-3** (Network Simulator 3) via an asynchronous subprocess bridge, paired with a self-contained, pure-Python discrete-event fallback engine.
* **Comparative Benchmark Matrix:** Evaluates all four queue-management disciplines concurrently against identical synthetic packet injection profiles (bursty distributions, Pareto transfers, continuous bulk TCP flows).
* **Architectural Isolation:** Strict boundary enforcement ensures zero simulation execution pathways interface with system-level traffic control controllers.

---

## Algorithmic Framework

SariChesko incorporates four foundational congestion-management mechanisms spanning **Traffic Shaping** (rate regulation) and **Active Queue Management** (bufferbloat mitigation):

| Algorithm | Taxonomic Class | Operational Principle | Primary Efficacy Regime |
| :--- | :--- | :--- | :--- |
| **Leaky Bucket** | Traffic Shaping | Queues inbound bursts and discharges packets at a strict, constant egress rate ($\rho$). | Eliminating egress jitter; enforcing deterministic downstream bitrates. |
| **Token Bucket** | Traffic Shaping | Accumulates transmission tokens at rate $r$ up to capacity $b$; permits bounded bursts of length $\le b$. | Accommodating burst-tolerant workflows while bounding sustained utilization. |
| **Random Early Detection (RED)** | Active Queue Management | Computes exponential weighted moving average queue length ($avg$); drops packets probabilistically between thresholds $[min_{th}, max_{th}]$. | Preventing global TCP synchronization and buffer saturation in intermediate buffers. |
| **Controlled Delay (CoDel)** | Active Queue Management | Tracks packet sojourn time (dwell duration in queue); triggers early drops only when minimum delay exceeds `target` over an `interval`. | Combating bufferbloat in variable-bandwidth links without manual buffer tuning. |

> [!NOTE]
> No single queuing discipline is universally optimal. Network topology, path symmetry, and workload burstiness determine algorithm efficacy. SariChesko evaluates empirical telemetry before issuing a tailored recommendation.

---

## Multi-Hop Fault Attribution & ISP Outage Detection

To prevent erroneous local configuration changes during upstream failures, SariChesko executes a tiered probing sequence across progressive hops:

```text
[Host Interface]
       │
       ▼ Level 0: Loopback Interrogation (Socket / Stack Sanity)
[Default Gateway]
       │
       ▼ Level 1: Local Access Point / LAN Router Interface
[First-Hop ISP PoP]
       │
       ▼ Level 2: Point of Presence / First Public Hop (ICMP Trace)
[Upstream WAN Transit]
       │
       ▼ Level 3: Tier-1 Anycast Targets (e.g., 8.8.8.8, 1.1.1.1)
[DNS Resolution Subsystem]
       │
       ▼ Level 4: Recursive Resolver Query & Latency Validation
[Application Layer CDN]
       ▼ Level 5: Edge Content Delivery Network Endpoint
```

### Diagnostic Decision Matrix

Empirical probe responses are evaluated against a deterministic fault matrix:

| Probe State Vector | Diagnostic Classification | Recommended Action |
| :--- | :--- | :--- |
| `Gateway Unreachable` | **Local Network / Physical Interface Fault** | Inspect local router, Wi-Fi link, or Ethernet interface. |
| `Gateway OK`, `ISP Hop Fails` | **Last-Mile / CPE Interface Degradation** | Cycle subscriber router; verify physical ISP link. |
| `ISP Hop OK`, `WAN Targets Fail` | **Upstream Transit / ISP Core Outage** | Upstream failure detected. Await ISP resolution. |
| `WAN OK`, `DNS Resolution Fails` | **Recursive Resolver Failure** | Switch to secondary/public DNS resolvers (e.g., Cloudflare, Quad9). |
| `WAN OK`, `DNS OK`, `High Latency / Loss` | **Transit Degradation or Carrier Throttling** | Path congestion upstream; local mitigation ineffective. |
| `All External Probes OK`, `Local Delay High` | **End-Host / Edge Congestion** | **Actionable:** Apply local shaping or AQM discipline. |

> [!IMPORTANT]
> When an upstream or ISP-side failure is verified, SariChesko strictly inhibits host-level qdisc modifications, preventing ineffective network disruptions.

---

## Heuristic Recommendation Engine

The engine employs a deterministic, fully explainable rule system (eliminating opaque black-box decisions in v1) to synthesize telemetry into concrete interventions:

| Detected Telemetry Signature | Recommended Remediation | Rationale |
| :--- | :--- | :--- |
| Bursty traffic with acceptable packet elasticity | **Token Bucket** | Preserves burst dynamics while constraining sustained transmission rates. |
| Deterministic downstream rate required; strict jitter bound | **Leaky Bucket** | Forces constant egress spacing; queues or clips exceeding instantaneous bursts. |
| Rapid buffer depth escalation; early queue growth | **Random Early Detection (RED)** | Induces early packet drops to trigger TCP window back-off before queue overflows. |
| Persistent packet dwell time (elevated queue sojourn delay) | **Controlled Delay (CoDel)** | Drops packets based on dwell time rather than queue depth, mitigating bufferbloat. |
| External hop failure / Carrier transit degradation | **Null Action (External Issue)** | Problem originates beyond host jurisdiction; local remediation suspended. |

Each recommendation generates an audit trail detailing the telemetry vectors (RTT, jitter, queue size, loss rate) that led to the verdict.

---

## System Architecture

The application is structured into four cleanly decoupled tiers adhering to separation-of-concerns principles:

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                       PRESENTATION LAYER (PySide6)                      │
│   Dashboard View   │   Live Telemetry View   │   Diagnostic Run View    │
│   Simulation Lab   │   Algorithm Comparison  │   History & Reports      │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Qt Signals & Slots
┌────────────────────────────────────▼────────────────────────────────────┐
│                        CORE ORCHESTRATION LAYER                         │
│   ┌───────────────────────────┐     ┌───────────────────────────────┐   │
│   │ Telemetry Monitor Engine  │     │ Sequential ISP Multi-Probe    │   │
│   ├───────────────────────────┤     ├───────────────────────────────┤   │
│   │ Congestion Scorer (0-100) │     │ Diagnostic Orchestrator       │   │
│   ├───────────────────────────┤     ├───────────────────────────────┤   │
│   │ Rule Recommendation Engine│     │ Traffic Control Safe Manager  │   │
│   └───────────────────────────┘     └───────────────────────────────┘   │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────────────┐
│                    PLATFORM ABSTRACTION LAYER (PAL)                     │
│          NetworkMonitor                   TrafficController             │
│   ┌─────────────────────────────┐   ┌─────────────────────────────┐     │
│   │ Windows: WTC / Netsh / WMI  │   │ Windows: QoS Policies / WTC │     │
│   │ Linux:   sysfs / rtnetlink  │   │ Linux:   tc (iproute2)      │     │
│   └─────────────────────────────┘   └─────────────────────────────┘     │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────────────────┐
│                         PERSISTENCE LAYER (SQLite)                      │
│   Sessions  •  Baselines  •  Metric Snapshots  •  ISP Probes            │
│   Diagnostic Runs  •  Applied Policies  •  Simulation Result Records   │
└─────────────────────────────────────────────────────────────────────────┘
```

### Directory Structure

```text
SariChesko/
├── sarichesko/
│   ├── app.py                          # Application entry point & Qt bootstrap
│   ├── platform/                       # Platform Abstraction Layer (PAL)
│   │   ├── base.py                     # Abstract Base Classes (Monitor, Controller)
│   │   ├── windows/
│   │   │   ├── monitor.py              # Windows WMI & socket performance counters
│   │   │   └── controller.py           # Windows QoS & netsh traffic control adapter
│   │   └── linux/
│   │       ├── monitor.py              # Linux sysfs & procfs network telemetry
│   │       └── controller.py           # Linux iproute2 / tc qdisc manager
│   ├── core/
│   │   ├── monitor_engine.py           # Background polling daemon & anomaly detector
│   │   ├── isp_probe.py                # Hierarchical multi-target reachability probe
│   │   ├── congestion_scorer.py        # Composite heuristic scoring engine (0–100)
│   │   ├── diagnostics_engine.py       # End-to-end diagnostic pipeline coordinator
│   │   ├── recommendation_engine.py    # Deterministic rule-based algorithm selector
│   │   └── traffic_control_manager.py  # Safe execution, verification & rollback
│   ├── simulation/
│   │   ├── ns3_bridge.py               # Subprocess bridge to ns-3 runtime
│   │   ├── python_sim.py               # Pure-Python discrete-event simulation engine
│   │   ├── scenarios/                  # Workload profiles (bulk transfer, bursty)
│   │   └── algo_runners/               # Leaky Bucket, Token Bucket, RED, CoDel runners
│   ├── storage/
│   │   ├── db.py                       # SQLite connection pool & schema migrations
│   │   ├── models.py                   # Data transfer objects & relational models
│   │   └── repository.py               # Encapsulated query & transaction operations
│   └── ui/
│       ├── main_window.py              # Shell frame, status bar & navigation dock
│       ├── views/                      # Modular view controllers
│       └── widgets/                    # Reusable visualizers (PyQtGraph / Matplotlib)
├── tests/                              # Unit & integration test suites
├── packaging/                          # PyInstaller specifications & installer scripts
├── pyproject.toml                      # Project build configuration & dependency manifest
└── requirements.txt                    # Pinned Python package dependencies
```

---

## Technical Specifications

| Subsystem | Technology | Purpose & Architectural Rationale |
| :--- | :--- | :--- |
| **GUI Framework** | PySide6 (Qt 6 for Python) | Hardware-accelerated, native desktop presentation across platforms. |
| **Telemetry Charting** | PyQtGraph & Matplotlib | Real-time 60 FPS multi-trace rendering with minimal CPU overhead. |
| **Local Storage** | SQLite 3 | Fully local, zero-configuration embedded persistence engine. |
| **Network Simulation** | ns-3 / Discrete Event Python | Academic-grade discrete-event packet simulation with a portable fallback. |
| **Linux Traffic Control** | `tc` via `iproute2` | Direct kernel egress queuing discipline (`qdisc`) configuration. |
| **Windows Traffic Control**| `netsh` / Windows Policy QoS | Platform-native network throttling and traffic marking. |
| **System Telemetry** | `psutil` + native OS sockets | Non-intrusive retrieval of NIC bytes, packet drops, and socket states. |
| **Distribution / Build** | PyInstaller | Standalone binary bundling for Windows (`.exe`) and Linux (`ELF`). |

---

## Safety & Defensive Engineering Invariants

Given that modifying network parameters can compromise host connectivity, SariChesko implements strict defensive invariants:

1. **Explicit Human-in-the-Loop Authorization:** The application never silently mutates operating system configurations. Every policy change requires explicit confirmation through a structured modal dialog detailing the exact command and parameters.
2. **Principle of Least Privilege:** SariChesko does not execute with permanent administrative/root privileges. Elevated access is requested transiently through native elevation prompts (`sudo` / UAC) only at the moment of actuation.
3. **Pre-Flight State Snapshotting:** The exact operational state of network interfaces and existing queuing disciplines is serialized prior to any mutation.
4. **Closed-Loop Empirical Verification:** After applying a policy, the system monitors link performance over a mandatory 30-second observation window, evaluating latency, jitter, and throughput against the pre-intervention baseline.
5. **Deterministic One-Click Rollback:** If the post-intervention state exhibits regression or fails to resolve the bottleneck, the user is prompted to restore the initial configuration with a single click.
6. **ISP-Isolation Barrier:** If multi-hop probing localizes the degradation to an upstream hop, host traffic mutation is prevented by design.
7. **Simulation Isolation:** The simulation subsystem executes in an isolated sandbox with no code paths leading to the Platform Abstraction Layer's actuators.

---

## Development Roadmap & Milestones

```text
Phase 1: Architecture Foundation    [Done] Core application shell, navigation, SQLite, themes
Phase 2: Real-Time Telemetry        [Done] Multi-interface monitoring, baselining, anomaly flags
Phase 3: Diagnostics & ISP Probing  [Done] Multi-hop probing pipeline & composite congestion scoring
Phase 4: Simulation Laboratory      [Done] ns-3 bridge integration & pure-Python discrete-event fallback
Phase 5: Recommendation Engine      [Done] Rule-based deterministic algorithm recommendation logic
Phase 6: Platform Traffic Control   [Done] Linux (tc) and Windows (QoS) actuation with privilege gating
Phase 7: Verification & Recovery    [Done] Closed-loop post-change validation and rollback mechanics
Phase 8: Packaging & Validation     [In Progress] Cross-platform installer builds & automated test suites
```

---

## Platform Support Matrix

| Platform | Telemetry Monitoring | Multi-Hop ISP Diagnostics | Simulation Lab | Kernel Traffic Actuation |
| :--- | :---: | :---: | :---: | :---: |
| **Linux** (Kernel 5.4+) | Supported (`sysfs`/`proc`) | Supported (Raw Sockets) | Supported (ns-3 / PySim) | Supported (`iproute2` / `tc`) |
| **Windows** (10 / 11) | Supported (`psutil`/`WMI`) | Supported (WinSock) | Supported (ns-3 / PySim) | Supported (`netsh` / QoS API) |
| **macOS** (Darwin) | Experimental | Experimental | Supported (PySim only) | Unsupported (Deferred to v2) |

---

## License & Attribution

Distributed under the **MIT License**. Refer to the [LICENSE](LICENSE) file for terms of redistribution and warranty disclaimers.

Contributions, academic citations, and issue submissions are welcome. When utilizing SariChesko in academic coursework or research, please cite this repository as a Computer Networks Project-Based Learning implementation.