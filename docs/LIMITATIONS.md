# KNOWN LIMITATIONS & THREATS TO VALIDITY

In accordance with academic integrity and rigorous systems engineering practices, this document details all architectural, data, and infrastructural limitations of **NetSim-RT**.

---

## 1. Trace Data & Service-Time Inferences
1. **Historical Trace Age**:
   - The primary HTTP datasets (NASA Kennedy Space Center, ClarkNet, Saskatchewan, EPA, SDSC) were recorded in 1995. Web architecture in 1995 predominantly used HTTP/1.0 without persistent connections (keep-alive) or multiplexing (HTTP/2, HTTP/3).
   - *Mitigation*: We incorporate the modern **Azure Functions 2021 Invocation Trace**, which contains cloud-native microservice invocation times spanning 2021.
2. **Derived Service Time Model for 1995 Access Logs**:
   - Standard Common Log Format (CLF) captures request arrival time, HTTP status, and response bytes, but does *not* record internal server processing latency or service time.
   - *Honest Disclosure*: Service times for web server logs are derived via $T_{\text{service}} = s_0(\text{class}) + \text{bytes} / B_{\text{eff}}$. While $s_0$ and $B_{\text{eff}}$ are calibrated against real measurements on `sys1`, they remain a calibrated model rather than hardware-measured 1995 server CPU clocks.
3. **Absence of a Stateful Relational Database Engine in Emulation**:
   - The real-server testbed on `sys1` emulates transactional booking logic with cryptographic hashing, simulated locks, and variable compute loads rather than executing heavy multi-table SQL queries against a live PostgreSQL or MySQL cluster.

---

## 2. Server Environment & Hardware Boundaries
1. **Containerized `sys1` Host**:
   - `stu137_sys1` operates within a containerized Linux environment without systemd as PID 1.
   - *Consequence*: Nested Docker (`dockerd` daemon within container) cannot be started due to lack of nested cgroup privileges (`docker: unrecognized service`).
   - *Solution*: Production deployment uses native Python virtual environments, isolated process daemons with PID tracking, and an Nginx reverse proxy binding to the assigned external ports (3507, 4507, 6507, 5507).
2. **Single-Host Emulation Testbed**:
   - Both the load generator client and the FastAPI/Nginx target servers reside on the same physical host (`sys1`).
   - *Potential Threat*: Client traffic generation could steal CPU cycles from the server processes.
   - *Mitigation*: Strict CPU affinity pinning via `taskset` ensures that the load generator and server worker pools run on disjoint sets of CPU cores (e.g., workers pinned to cores 0-5, load generator pinned to cores 6-9).

---

## 3. Simulator Scope & Modeling Boundaries
1. **Network Layer Abstractions**:
   - The discrete-event engine models application-layer requests, HTTP connection pools, concurrency limits, and server queues.
   - Low-level TCP phenomena (such as TCP slow start, packet loss retransmissions, SYN flood backlogs, and intermediate BGP routing delays) are abstracted into bounded network delay models.
2. **Custom Policy AST Sandbox Constraints**:
   - To guarantee complete host security against arbitrary code execution, the custom policy sandbox restricts Python standard libraries (no external imports, no filesystem I/O, no network calls).
   - Policies that require heavy external machine learning libraries (such as PyTorch or TensorFlow) must be evaluated offline or integrated into built-in engine modules.

## Latency Floor
DES matches throughput and ordering of policies; absolute latency differs by the measured floor (~1.0-1.8ms HTTP/IPC overhead not modeled in DES); tail diverges at saturation due to CFS preemption and OS scheduling jitter.
