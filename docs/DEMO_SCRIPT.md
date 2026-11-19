# NetSim-RT Demonstration Scripts

> **CSL559 - Computer Systems Design**  
> **Course Project:** NetSim-RT: Trace-Driven Real-Traffic Simulator & Policy Benchmark  
> **Panel Demo Date:** Friday, 20 Nov 2026, 11:45 AM  
> **Authors:** Kinshuk Gupta (12341190), Maloth Madhu (12341370), Bhukya Raju (12340520)

---

## Part 1: 5-Minute No-Narration YouTube Video Flow
*(Designed for high-definition screen recording with on-screen text overlays, exact click paths, and sub-second transitions)*

| Timecode | Visual Screen State | Action & Click Path | On-Screen Overlay Text Banner |
| :--- | :--- | :--- | :--- |
| **0:00 - 0:35** | Home page: Header pill (`CSL559`), active Presets Tab. Grid of 6 scenario cards. | Smooth hover over cards. Click `"Inspect Scenario"` on Card 1 (Baseline Workload). Scroll smoothly to preset chart. | **NetSim-RT: Trace-Driven Real-Traffic Discrete-Event Simulator**<br>*Precomputed benchmarks loaded from DuckDB in <1s. Baseline FCFS queueing on EPA 1995 trace.* |
| **0:35 - 1:15** | Presets Tab: Inspect Flash Crowd and Load Sweep cards. | Click `"Inspect Scenario"` on Card 4 (Load Sweep). View Phase Transition point cards (Knee: 69.7x, Inflection: 114.8x, Breaking: 311.6x). | **Phase Transitions: Knee (81.8ms), Inflection (199.1ms), Breaking Point (500.4ms)**<br>*Automated maximum-curvature detection (Kneedle algorithm) and SLO breach tracking.* |
| **1:15 - 2:00** | Presets Tab: Card 5 (Retry Storm) and Card 6 (Policy Shootout). | Click `"Inspect Scenario"` on Card 6 (Shootout). Observe comparative bar chart and metrics table (FCFS vs SJF vs RR vs Priority). | **Multi-Policy Shootout: Tail Latency vs. Fairness Trade-Offs**<br>*Round Robin maximizes Jain Fairness (0.899); Priority causes starvation on browse traffic (0.589).* |
| **2:00 - 2:55** | Switch to **Simulator Tab** via Top Navigation bar. | Select `NASA Kennedy Space Ctr (Jul 95)`, set `Servers = 4`, `Load Multiplier = 2.0`, `Policy = SJF`. Click `"Run Simulation"`. | **Interactive DES Engine: Replaying Real Production Traces (NASA Jul 95)**<br>*Over 330,000 events/second. Dynamic queue depth and busy worker timeline rendered in real-time.* |
| **2:55 - 3:45** | Switch to **Load Sweep Tab**. | Select `EPA Web Server`, set `Policy = FCFS`, click `"Run Load Sweep"`. Sweep curve animates across 25 logarithmic load points. | **Automated 25-Point Load Sweep (0.1x to 400x Load)**<br>*Detects operational collapse before queue explosion occurs.* |
| **3:45 - 4:25** | Switch to **Custom Policy Sandbox Tab**. | Click `"Load Code"` template (`Shortest Job First + Priority`). Click `"Execute Sandboxed Simulation"`. | **AST Security Sandbox: In-Browser Custom Policy Authoring**<br>*Syntax whitelist blocks unauthorized syscalls; enforces setrlimit quotas and fallback FCFS.* |
| **4:25 - 5:00** | Switch to **Architecture Tab**. | View high-resolution System Architecture & Experimental Methodology diagrams. Show terminal with 14 passing unit tests (`pytest`). | **Rigorous Computer Systems Design & Queueing Foundations**<br>*Verified against M/M/m Jackson closed forms. Live on sys1: http://10.1.75.40:3507* |

---

## Part 2: 10-Minute Live Viva Flow

### 0:00 - 2:00: Problem Formulation & CSD Motivation (Presenter: Kinshuk Gupta)
- **The Core Problem:** Synthetic Poisson traffic fails in production systems because real traffic exhibits self-similarity (Hurst parameter $H > 0.90$), heavy-tailed request sizes, and multi-scale diurnal bursts.
- **System Architecture:** Walk through the end-to-end discrete event engine pipeline (`docs/architecture.png`): Parquet trace ingestion -> windowing -> admission control -> load balancing (Central, RR, JSQ, SQ2) -> multi-server queue scheduling -> DuckDB persistence -> FastAPI / ECharts frontend.

### 2:00 - 4:30: Stability Boundaries & Load Sweep (Presenter: Maloth Madhu)
- **Phase Transition Theory:** Explain why latency stays flat at low load, then explodes non-linearly.
- **The Three Critical Points:**
  - *Knee Point:* Maximum curvature boundary identified using the Kneedle algorithm (Satopaa et al. 2011). Identifies safe operational capacity headroom.
  - *Inflection Point:* Curvature zero-crossing ($d^2 L / d\lambda^2 = 0$), where queue growth transitions from exponential acceleration to arrival-rate saturation.
  - *Breaking Point:* The load multiplier where $p99$ tail latency breaches the strict 500ms SLO target or goodput collapses.
- **Live Demo:** Trigger a real-time load sweep on the EPA trace, highlighting the detected transition points.

### 4:30 - 7:00: Policy Shootout, Fairness & Outage Dynamics (Presenter: Bhukya Raju)
- **The Classical Trade-Off:**
  - *SJF/SRTF:* Optimal mean waiting time (Harchol-Balter), but starves large jobs under sustained high load.
  - *Round Robin (RR):* Time-slicing quantum ($q = 10\text{ms}$) guarantees bounded delay and maximum Jain's fairness index ($J = 0.899$).
  - *Priority Scheduling:* Guarantees low latency for critical transactions (`book`), but drops background fairness to $J = 0.589$.
- **Hurricane Erin Outage Recovery:** Demonstrate the historical 37.7-hour shutdown of Kennedy Space Center in August 1995 and show how multi-server queues drain the post-reopening surge.
- **Retry Storms:** Show traffic amplification and goodput collapse when client timeout is shorter than queue dwell time.

### 7:00 - 8:30: Custom Policy Sandbox & Security (Presenter: Kinshuk Gupta)
- **Security Sandbox:** Explain the multi-layer containment:
  1. *AST Node Inspection:* Rejects `Import`, `Call` to builtins like `open`/`eval`, attribute tampering (`__class__`), and file I/O.
  2. *OS Resource Limits:* Subprocess isolation with `setrlimit(RLIMIT_AS, 256MB)` and `setrlimit(RLIMIT_CPU, 2s)`.
  3. *Fail-Safe Fallback:* Any policy crash or timeout automatically fails over to baseline FCFS without bringing down the server.
- **Live Demo:** Modify the custom policy in the editor to prioritize short booking requests, run the simulation, and inspect the resulting fairness delta.

### 8:30 - 10:00: Panel Q&A & Verification (All Team Members)
- Address panel questions regarding queueing bounds ($M/G/c$ vs $M/M/c$), Little's Law verification ($L = \lambda W$), trace calibration limits, and sys1 deployment architecture.
