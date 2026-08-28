# SariChesko

> **Telugu:** *"Fix it / Sort it out"*

A real, open-source, cross-platform desktop application for detecting, diagnosing, and managing network congestion — with built-in ISP outage detection. Built as a Computer Networks PBL project demonstrating four classic adaptive congestion-management algorithms.


## What it does

SariChesko monitors your network in real-time, detects congestion, figures out whether the problem is on your side or your ISP's side, explains what it found in plain English, recommends the right algorithm to fix it, asks your permission before touching anything, applies the fix, and then verifies whether it actually helped. If it didn't, it rolls back.

Core workflow:
Monitor → Detect → Diagnose → Explain → Recommend → Ask Permission → Apply → Verify

---

## Two Modes

### Mode A — Real Network
- Live interface detection and monitoring
- Baseline and loaded-state measurement
- Anomaly detection against your personal baseline
- OS-level traffic control with explicit permission
- Before/after verification — never just says "done"
- Full rollback if the fix doesn't help

### Mode B — Simulation Lab
- Safe, repeatable experiment environment
- Powered by **ns-3** (with a clean Python-only fallback if ns-3 is not installed)
- Compare all four algorithms side-by-side on identical synthetic traffic
- No risk to your real network

---

## The Four Congestion Algorithms

| Algorithm | Type | When it helps |
|-----------|------|---------------|
| **Leaky Bucket** | Traffic shaping | Smooth out bursty traffic into a steady fixed-rate stream |
| **Token Bucket** | Traffic shaping | Shape traffic while allowing controlled, legitimate bursts |
| **RED** (Random Early Detection) | Active Queue Management | Probabilistically drop packets early when queues grow too fast |
| **CoDel** (Controlled Delay) | Active Queue Management | Target excessive queueing delay (sojourn time), not queue size |

No algorithm is always best. SariChesko measures your actual conditions and recommends the right one with an explanation.

---

## ISP Issue & Outage Detection

SariChesko probes multiple targets in sequence to pinpoint where the problem actually is:


Level 0 — Loopback (sanity check)
Level 1 — Your default gateway (home router)
Level 2 — First ISP hop (first public IP in traceroute)
Level 3 — WAN hosts (8.8.8.8, 1.1.1.1)
Level 4 — DNS resolution check
Level 5 — CDN endpoint


**Diagnosis verdicts:**
| Probe result | Verdict |
|---|---|
| Gateway fails | Local network / router issue |
| Gateway OK, ISP hop fails | Last-mile / ISP CPE issue |
| ISP hop OK, WAN fails | ISP upstream outage |
| WAN OK, DNS fails | DNS resolver issue |
| WAN OK, DNS OK, but slow | ISP throttling / degradation |
| All OK, high local latency | Local congestion — apply a fix |

If the problem is on your ISP's side, SariChesko tells you that instead of trying to apply a local fix that won't help.

---

## Recommendation Engine

Rule-based and fully explainable (no ML or AI black boxes in v1):

| Observed condition | Recommended algorithm |
| Bursty traffic + bursts acceptable | Token Bucket |
| Need smooth, steady output | Leaky Bucket |
| Queue growing rapidly | RED |
| Persistent queueing delay | CoDel |
| ISP-side issue detected | No local fix — contact ISP |

Every recommendation comes with a plain-English explanation of why.

---

## Architecture
┌─────────────────────────────────────────────────────────────┐
│                      UI LAYER (PySide6/Qt)                  │
│  Dashboard │ Diagnose │ Live Network │ Simulation Lab        │
│  Compare Algorithms │ History │ Reports │ Settings           │
└───────────────────────┬─────────────────────────────────────┘
                        │ Qt signals / slots
┌───────────────────────▼─────────────────────────────────────┐
│                    APPLICATION CORE                         │
│  Monitor Engine │ ISP Probe │ Congestion Scorer             │
│  Diagnostics Engine │ Recommendation Engine                 │
│  Traffic Control Manager │ Simulation Engine                │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│              PLATFORM ABSTRACTION LAYER (PAL)               │
│      NetworkMonitor            TrafficController             │
│   Windows impl | Linux impl  Windows impl | Linux impl      │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────────┐
│                   STORAGE LAYER (SQLite)                    │
│  Sessions │ Measurements │ Baselines │ ISP Diagnostics      │
│  Diagnostic Runs │ Applied Policies │ Simulation Results    │
└─────────────────────────────────────────────────────────────┘

### Project Structure
SariChesko/
├── sarichesko/
│   ├── app.py                        # Entry point
│   ├── platform/                     # OS abstraction (Windows + Linux)
│   │   ├── base.py                   # Abstract interfaces
│   │   ├── windows/monitor.py
│   │   ├── windows/controller.py     # netsh / Windows Traffic Control API
│   │   ├── linux/monitor.py
│   │   └── linux/controller.py       # tc / iproute2 qdisc
│   ├── core/
│   │   ├── monitor_engine.py         # Background polling, anomaly detection
│   │   ├── isp_probe.py              # Multi-target ISP/outage detection
│   │   ├── congestion_scorer.py      # Composite 0–100 congestion score
│   │   ├── diagnostics_engine.py     # Orchestrates a full diagnostic run
│   │   ├── recommendation_engine.py  # Rule-based algo selection (pure functions)
│   │   └── traffic_control_manager.py # Human-in-the-loop, apply, verify, rollback
│   ├── simulation/
│   │   ├── ns3_bridge.py             # ns-3 subprocess bridge
│   │   ├── python_sim.py             # Pure-Python discrete-event fallback
│   │   ├── scenarios/                # bulk_transfer, bursty_traffic, ...
│   │   └── algo_runners/             # leaky_bucket, token_bucket, red, codel
│   ├── storage/
│   │   ├── db.py                     # SQLite connection + migrations
│   │   ├── models.py                 # Dataclasses mirroring schema
│   │   └── repository.py            # All read/write ops
│   └── ui/
│       ├── main_window.py
│       ├── views/                    # One file per nav screen
│       └── widgets/                  # Reusable chart and dialog widgets
├── tests/
├── packaging/
├── pyproject.toml
└── requirements.txt
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| UI | PySide6 (Qt for Python) |
| Charts | PyQtGraph + Matplotlib |
| Database | SQLite (local, no cloud) |
| Simulation | ns-3 + Python fallback |
| Traffic control (Linux) | `tc` / iproute2 |
| Traffic control (Windows) | `netsh` / Windows QoS / WTC API |
| Network monitoring | `psutil` + OS APIs |
| Packaging | PyInstaller |

---

## Safety Design

- **Never silently changes network settings.** Every OS-level action requires explicit user confirmation in a dialog.
- **Elevated privileges only when needed.** The app does not run as admin/root — it requests elevation only for the specific action that needs it.
- **Always saves state before applying.** Full config snapshot is taken before any change.
- **Always verifies after applying.** 30 seconds of post-change measurement compared against the pre-change baseline.
- **Rollback offered if verification fails.** One click restores to exactly the saved snapshot.
- **ISP issues are never "fixed" locally.** If the problem is upstream, the app reports it and suggests contacting your ISP rather than applying a pointless local policy.
- **Simulation is completely isolated from real network control.** No path between the simulation engine and the traffic controller exists in the code.

---

## Development Phases

| Phase | What gets built |
|-------|----------------|
| 1 | Desktop foundation — app shell, navigation, SQLite, theme |
| 2 | Network monitoring — live stats, baseline, anomaly detection |
| 3 | Diagnostics & ISP detection — congestion scoring, ISP probe |
| 4 | Simulation Lab — ns-3 bridge, Python fallback, algorithm runners |
| 5 | Recommendation engine — rule-based algo selection |
| 6 | Real traffic control — OS-level apply with permission dialog |
| 7 | Verification & rollback — before/after comparison, rollback |
| 8 | Packaging — PyInstaller, .desktop file, install scripts |

---

## Platform Support

Windows and Linux are **equal first-class targets** — not a primary + port. Every feature works on both, or is honestly reported as unsupported on that platform. macOS support is not planned for v1.

---

## License

MIT — open-source, contributions welcome.