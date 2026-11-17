# ASSUMPTIONS & DESIGN DECISIONS

This document logs all principal engineering and architectural decisions made autonomously for **NetSim-RT** (Repo: `netsim-rt-csl559`, Project Slot: Real Traffic Simulator, Theme: RealTimeBookingSystem, Course: CSL559 Computer Systems Design, IIT Bhilai).

---

## 1. System Environment & Server Architecture (`sys1`)
- **Host Characteristics**: `stu137_sys1` (Internal IP `172.17.0.9`, external access via port 2507). 10 vCPU, 10 GiB RAM assigned, Linux kernel 6.8.0.
- **Containerized Environment**: sys1 runs within an unprivileged container environment without systemd init (PID 1 is not systemd).
- **Process Orchestration Decision**:
  - Instead of nested Docker (which requires privileged cgroups/dockerd daemon), services on sys1 are orchestrated using an isolated native Python 3.12 virtual environment, dedicated background daemon workers with PID tracking, and a production Nginx reverse proxy.
  - Verification is performed via HTTP health checks on `http://10.1.75.40:3507`.
- **Port Allocation Strategy**:
  - `3507`: Production Web UI (Nginx static bundle + reverse proxy `/api/` -> 4507).
  - `4507`: NetSim-RT Core FastAPI Backend & DES Sweep Engine.
  - `6507`: Emulation Target Service (real HTTP service for live replaying & calibration).
  - `5507`: Prometheus & telemetry metrics exporter.
  - `7507`: Spare benchmark / auxiliary port.
  - `2507`: Course SSH port.

---

## 2. Real Datasets & Trace Processing Pipeline
- **Strict Real-Data Mandate**: Zero synthetic data is used for application simulation, sweep benchmarks, or report figures. (Synthetic Poisson M/M/c traces are restricted strictly to `tests/` unit tests to mathematically verify Little's Law and Pollaczek-Khinchine closed-form limits).
- **Datasets Analyzed**:
  1. **NASA-HTTP** (Kennedy Space Center, Jul-Aug 1995, ~3.46M requests): Highlights diurnal patterns and the Hurricane Erin physical outage gap (01 Aug 14:52 to 03 Aug 04:36 UTC).
  2. **ClarkNet-HTTP** (~3.33M requests over two weeks): Commercial ISP traffic with high burstiness.
  3. **EPA-HTTP & SDSC-HTTP** (~47k and ~28k requests): Compact traces used for instant test suites and rapid live UI demonstrations.
  4. **Azure Functions 2021 Trace**: Cloud serverless trace providing true recorded invocation durations (ms) without estimation.
  5. **Saskatchewan-HTTP** (~2.4M requests): Multi-month academic access trace.
- **Service Time Modeling for HTTP Access Logs**:
  - Standard HTTP access logs (Common Log Format) record timestamps, remote hosts, requested URIs, HTTP status codes, and transferred bytes, but not processing latency.
  - We derive realistic service times using:
    $$T_{\text{service}} = s_0(\text{class}) + \frac{\text{bytes}}{B_{\text{eff}}}$$
    where:
    - $\text{class} = \text{book}$ for dynamic/transactional endpoints (e.g., `/cgi-bin/`, POSTs, booking operations): calibrated $s_0 \in [20, 60] \text{ ms}$.
    - $\text{class} = \text{browse}$ for static assets (e.g., `.html`, `.gif`, `.jpg`): calibrated $s_0 \in [1, 5] \text{ ms}$.
    - $B_{\text{eff}}$ is the effective server I/O bandwidth, calibrated against real sys1 testbed measurements.
  - For Azure Functions traces, true invocation execution times are utilized directly.

---

## 3. Discrete-Event Simulator (DES) Architecture
- **Heap-based Engine**: Implemented in Python 3.12 utilizing standard library `heapq` and contiguous `numpy` arrays for timestamp management, avoiding SimPy's Python generator overhead (achieving $>100,000$ events/sec per worker).
- **Parallel Sweep Execution**: Multi-point load multiplier sweeps ($0.1\times$ to $50\times$, 25 log-spaced points) leverage Python's `concurrent.futures.ProcessPoolExecutor` utilizing up to 10 CPU cores on sys1.
- **Deterministic Replay**: Fixed pseudo-random seeds guarantee reproducible queueing outcomes across comparative policy sweeps.

---

## 4. Special Points Identification
- **Knee Point**:
  - Determined using the Kneedle algorithm (`kneed.KneeLocator`) on the convex $p99$ latency vs. offered load curve. Identifies the point of maximum curvature where queueing delay begins rapid non-linear expansion.
- **Inflection Point**:
  - The zero-crossing of the second derivative ($\frac{d^2 \text{Latency}}{d \lambda^2} = 0$) calculated via smoothed cubic splines (`scipy.interpolate.UnivariateSpline`). Marks the transition from accelerating queueing delay to queue-saturation plateaus.
- **Breaking Point**:
  - The lowest offered load multiplier $\lambda$ where:
    $$\text{Latency}_{p99}(\lambda) > \text{SLO} \quad (500\text{ ms default}) \quad \lor \quad \text{Goodput}(\lambda) < 0.95 \times \text{Offered Load}(\lambda)$$

---

## 5. Sandboxed Custom Policy Execution
- **Threat Model**: User-supplied Python code in the browser must not execute unauthorized system calls, inspect private memory, import unauthorized modules, or hang the server.
- **Defense-in-Depth Sandbox**:
  1. **AST Allowlist**: Inspects abstract syntax tree prior to execution; rejects `Import`, `ImportFrom`, `Call` to unapproved builtins, attribute access starting with `__`, and system keywords (`exec`, `eval`, `open`, `os`, `sys`).
  2. **Isolated Subprocess Execution**: Policy evaluation runs in a separated worker process bounded by POSIX resource limits (`setrlimit` for `RLIMIT_CPU` = 1.0s, `RLIMIT_AS` = 128MB).
  3. **Strict Time Budget & Safe Fallback**: Per-invocation step budget of 5ms. Any timeout, exception, or policy failure automatically logs a descriptive UI alert and safely falls back to standard FCFS scheduling.

---

## 6. Real-Server Emulation & Testbed Calibration
- **Real-World Validation Setup**:
  - A real FastAPI/uvicorn server runs on port 6507 behind an Nginx reverse proxy with real worker processes pinned to specific CPU cores using `taskset`.
  - An asynchronous trace-replay load generator replays real timestamps against the target.
  - Real round-trip latencies, drop rates, and throughput are measured and persisted to `results/validation/` to validate against DES predictions.
