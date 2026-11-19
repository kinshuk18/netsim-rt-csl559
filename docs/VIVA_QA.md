# NetSim-RT Viva Voce Questions & Answers (40 Comprehensive Q&As)

> **Course:** CSL559 - Computer Systems Design  
> **Project:** NetSim-RT: Trace-Driven Real-Traffic Simulator & Policy Benchmark  
> **Team:** Kinshuk Gupta [KG] (12341190), Maloth Madhu [MM] (12341370), Bhukya Raju [BR] (12340520)

---

### Section 1: Queueing Theory, Traffic Intensity & Stability Boundaries

#### Q1 [KG]: What is traffic intensity $\rho$, and what happens when $\rho \ge 1$?
**A:** In a multi-server $M/G/c$ system, traffic intensity is defined as $\rho = \frac{\lambda E[S]}{c} = \frac{\lambda}{c \mu}$, where $\lambda$ is average arrival rate, $E[S]$ is mean service time, and $c$ is the number of worker servers. If $\rho < 1$, the queue reaches a stationary ergodic steady-state. If $\rho \ge 1$, arrival rate exceeds total system service capacity; queue length $Q(t)$ grows without bound ($Q(t) \to \infty$), mean delay diverges, and any finite buffer causes massive drop rates.

#### Q2 [KG]: What mathematical law governs the relationship between queue length and wait time?
**A:** **Little's Law** ($L = \lambda W$), which states that the long-term average number of requests in a stationary queueing system ($L$) equals the long-term average effective arrival rate ($\lambda$) multiplied by the average time a request spends in the system ($W$). It holds independent of the arrival distribution or service time distribution (Little 1961).

#### Q3 [MM]: Why does queueing delay stay flat at low load but explode non-linearly near capacity?
**A:** According to the Pollaczek-Khinchine formula for $M/G/1$ and Kingman's heavy-traffic approximation for $G/G/c$:
$$W_q \approx \left(\frac{C_a^2 + C_s^2}{2}\right) \left(\frac{\rho}{1 - \rho}\right) E[S]$$
The term $\frac{\rho}{1 - \rho}$ exhibits an asymptotic singularity at $\rho = 1$. For $\rho \in [0, 0.6]$, $\frac{d}{d\rho}\left(\frac{\rho}{1-\rho}\right) = \frac{1}{(1-\rho)^2}$ is small, yielding flat latency. As $\rho \to 1$, the derivative explodes quadratically toward infinity.

#### Q4 [MM]: How does NetSim-RT mathematically define and detect the "Knee" of the load curve?
**A:** The Knee point is defined as the operational load of maximum curvature on the normalized load-latency curve $L(\lambda)$. We detect it using the **Kneedle algorithm** (Satopaa et al. 2011), which normalizes both axes to $[0, 1]$, draws a reference chord connecting the endpoints, and locates the point of maximum perpendicular distance between the curve and the chord.

#### Q5 [MM]: What is the operational distinction between the Knee, Inflection, and Breaking points?
**A:**
1. **Knee Point:** Onset of non-linear queue expansion (safe operational headroom boundary).
2. **Inflection Point:** The point where the second derivative changes sign ($d^2 L / d\lambda^2 = 0$), marking the transition from exponential delay acceleration to saturation rate limitation.
3. **Breaking Point:** Capacity collapse threshold where tail latency breaches the service SLO ($p99 > 500\text{ms}$) or goodput collapses below 95% of offered load.

#### Q6 [BR]: Why did our empirical breaking point occur at $\rho = 0.237$ rather than $\rho \approx 1.0$?
**A:** Because real workloads exhibit heavy-tailed job sizes ($C_s^2 \gg 1$) and bursty arrivals ($C_a^2 \gg 1$). Under heavy-tailed service distributions, rare massive requests monopolize servers, causing catastrophic head-of-line blocking for tail requests ($p99$). Thus, $p99$ latency breached the strict 500ms SLO target long before the mean server utilization reached 100%.

#### Q7 [KG]: How does variance in service time affect queueing delay?
**A:** As shown by the Pollaczek-Khinchine formula, average waiting time is directly proportional to $\frac{1 + C_s^2}{2}$, where $C_s^2 = \frac{\text{Var}(S)}{(E[S])^2}$ is the squared coefficient of variation. For exponential distributions $C_s^2 = 1$; for heavy-tailed Pareto distributions, $C_s^2 \gg 10$, amplifying waiting times by an order of magnitude under identical mean service times.

#### Q8 [BR]: What is the difference between open-loop and closed-loop workload models?
**A:** In an **open-loop** model (used in NetSim-RT trace replay), requests arrive according to external timestamps regardless of server state or backpressure. In a **closed-loop** model, new requests are only issued after previous requests complete (fixed concurrency). Real Internet traffic acts open-loop during flash crowds, which is why open-loop simulations reveal true catastrophic breakdown.

---

### Section 2: Scheduling Policies & Resource Trade-Offs

#### Q9 [KG]: Why does Shortest Job First (SJF) minimize mean wait time?
**A:** By Smith's rule and interchangeable arguments (Harchol-Balter 2013), scheduling the job with the shortest service time first maximizes the rate at which completed jobs leave the system, thereby draining the instantaneous queue length $Q(t)$ at the steepest possible rate and minimizing $\int Q(t) dt$.

#### Q10 [KG]: If SJF is optimal for mean wait time, why is it rarely used alone in general-purpose web servers?
**A:** Because SJF causes **starvation** of long jobs under high load. When arrival rate of short jobs is sufficiently high, long jobs never get scheduled, causing tail latency ($p99$) and maximum wait time to grow toward infinity.

#### Q11 [MM]: How does Shortest Remaining Time First (SRTF) differ from SJF?
**A:** SJF is non-preemptive; once a long job begins executing on a server, it runs to completion. SRTF is **preemptive**; if a new request arrives whose remaining service time is less than the current job's remaining time, the active job is paused and returned to the queue, and the shorter job preempts the server.

#### Q12 [MM]: What are the trade-offs of the Round Robin (RR) quantum size $q$?
**A:**
- If $q \to 0$ (Processor Sharing): Perfect fairness, short jobs complete quickly without knowing service times in advance, but context-switching overhead dominates real systems.
- If $q \to \infty$: Round Robin degenerates into FCFS, suffering head-of-line blocking.
- In NetSim-RT, $q = 10\text{ms}$ balances preemption responsiveness against context switching.

#### Q13 [BR]: What is Jain's Fairness Index and how is it calculated?
**A:** Proposed by Jain, Chiu, and Hawe (1984), Jain's Index measures whether shared system resources are allocated equitably:
$$J(x_1, x_2, \dots, x_n) = \frac{\left(\sum_{i=1}^n x_i\right)^2}{n \cdot \sum_{i=1}^n x_i^2}$$
where $x_i$ is normalized performance (e.g., service time divided by total sojourn time). $J \in [1/n, 1.0]$, where $1.0$ is completely fair. In our shootout, RR achieved $J = 0.899$ while Static Priority dropped to $J = 0.589$.

#### Q14 [BR]: How does Static Priority scheduling work in NetSim-RT?
**A:** Requests are categorized into transaction classes: `book` (checkout/write, high priority) and `browse` (read/search, low priority). The scheduler always serves `book` requests before any `browse` request. This isolates latency-sensitive revenues flows, but starves `browse` requests during load surges.

#### Q15 [KG]: How does Weighted Fair Queueing (WFQ) approximate Generalized Processor Sharing (GPS)?
**A:** GPS is an idealized continuous fluid-flow model where each active flow $i$ receives a service fraction $\frac{w_i}{\sum w_k}$. Because network and CPU packets are discrete, WFQ (Demers, Keshav, & Shenker 1989) computes a virtual finish time for each discrete job and schedules jobs in increasing order of virtual finish time.

#### Q16 [MM]: How does Multi-Level Feedback Queue (MLFQ) operate without prior knowledge of service times?
**A:** MLFQ maintains multiple priority queues ($Q_0, Q_1, \dots$). New requests enter at highest priority $Q_0$ with small quantum $q_0$. If a request does not complete within $q_0$, it is demoted to $Q_1$ with a larger quantum. Short jobs finish quickly in top queues (emulating SJF), while long jobs sink to bottom queues (emulating FCFS).

---

### Section 3: Load Balancing & Distributed Dispatching

#### Q17 [BR]: What is the architectural difference between a Central Queue ($M/G/c$) and Distributed Queues ($c \times M/G/1$)?
**A:**
- **Central Queue:** Single shared queue; whenever any server becomes idle, it pulls the next request. Prevents server idling while requests wait, but the central lock/dispatch creates a bottleneck at high concurrency.
- **Distributed Queues:** Front-end load balancer dispatches incoming requests to individual per-server queues. Highly scalable, but can lead to load imbalance where one queue is deep while another server sits idle.

#### Q18 [KG]: What is the Power of Two Choices (SQ2) and why is it superior to Random routing?
**A:** Demonstrated by Mitzenmacher (2001), when a request arrives, instead of querying all $c$ server queues or choosing uniformly at random, the load balancer randomly samples 2 servers and assigns the request to the shorter queue. This exponentially reduces maximum queue length from $O\left(\frac{\ln n}{\ln \ln n}\right)$ to $O(\ln \ln n)$ with minimal probing overhead.

#### Q19 [MM]: When does Join-Shortest-Queue (JSQ) break down?
**A:** Under very high arrival rates or when state updates are delayed (stale queue depth information). Probing all $c$ servers introduces network latency and synchronization contention, and stale metrics can cause "herd behavior" where hundreds of requests flood a previously idle server.

#### Q20 [BR]: How does Round Robin load balancing interact with heavy-tailed service times?
**A:** Round Robin dispatches requests sequentially across workers ($1, 2, \dots, c, 1, 2, \dots$). If a sequence of heavy jobs happens to land on the same worker, that worker's queue explodes while other workers remain lightly loaded, degrading overall system tail latency compared to JSQ or SQ2.

---

### Section 4: Admission Control, Retries & Metastability

#### Q21 [KG]: What is a retry storm and why does it cause catastrophic failure?
**A:** When server queues become saturated, request dwell time exceeds client-side timeouts ($T_{client}$). Clients assume packet loss and retry the request. The retried requests join the back of the queue, compounding offered load ($\lambda_{offered} = \lambda_{original} + \lambda_{retry}$). The servers spend CPU processing requests whose clients have already timed out, causing **goodput collapse** to near zero.

#### Q22 [MM]: What is the difference between Throughput and Goodput?
**A:**
- **Throughput:** Total number of requests completed by servers per unit time, regardless of whether the client still cares.
- **Goodput:** The rate of requests successfully completed *within the client timeout and service SLO* ($< 500\text{ms}$). In a retry storm, throughput may remain high while goodput collapses to zero.

#### Q23 [BR]: How does Token Bucket admission control prevent queue saturation?
**A:** A token bucket accumulates tokens at rate $r$ tokens/sec up to capacity $B$. A request must acquire a token before entering the queue. If the bucket is empty, the request is immediately rejected (HTTP 429 / drop-tail). This bounds the maximum sustained arrival rate to $r$ and maximum burst size to $B$, guaranteeing that downstream servers never exceed their capacity limit $\rho_{max}$.

#### Q24 [KG]: What is metastable failure in distributed systems?
**A:** A failure state where a temporary overload triggers a feedback loop (such as retry amplification, cache eviction, or GC thrashing) that sustains the degraded performance state *even after the original external trigger has disappeared*. Recovery requires shedding load completely or restarting components.

#### Q25 [MM]: How does exponential backoff with jitter mitigate retry storms?
**A:** Instead of retrying after a fixed interval $\Delta t$, clients wait $T_{backoff} = \min(T_{max}, T_{base} \cdot M^k) + \text{Uniform}(0, J)$, where $k$ is the retry attempt and $J$ is random jitter. Exponential backoff reduces offered rate over time, while jitter breaks synchronization phases that cause synchronized arrival waves.

---

### Section 5: Real-World Traces & Empirical Validity

#### Q26 [BR]: What empirical invariants did Arlitt & Williamson (1996) discover in web server access logs?
**A:** They identified ten invariant properties of HTTP workloads:
1. Document file sizes are heavy-tailed (Pareto distribution).
2. A small percentage of files accounts for the majority of requests and byte volume (Zipf-like distribution).
3. Request arrivals exhibit self-similarity and burstiness across multiple timescales.
4. HTTP transfers are predominantly read operations.

#### Q27 [KG]: What is the Hurst parameter $H$, and what does $H > 0.90$ signify in our traces?
**A:** The Hurst parameter measures long-range dependence (LRD) and self-similarity in time series. For memoryless Poisson processes, $H = 0.50$. For all five traces in NetSim-RT, $H \in [0.913, 0.980]$. This proves that traffic bursts do not smooth out over time, and arrival clusters persist across minutes and hours.

#### Q28 [MM]: Why did the NASA Kennedy Space Center trace show a 37.7-hour gap in August 1995?
**A:** On August 1–3, 1995, Hurricane Erin swept across Central Florida, prompting the physical evacuation and power shutdown of the Kennedy Space Center facilities. When power was restored on August 3, 1995, server logs captured an immediate post-reopening surge of accumulated worldwide traffic.

#### Q29 [BR]: How did NetSim-RT calibrate request service time for 1995 traces that lacked latency logs?
**A:** In accordance with empirical HTTP/1.0 transfer modeling (Arlitt & Williamson 1996), service time was derived from response payload size:
$$S = \frac{\text{Bytes}}{\text{Bandwidth}} + L_{cpu}$$
where bandwidth was calibrated to historical Ethernet rates (10 Mbps) and $L_{cpu}$ represents the base kernel socket setup and disk read latency (2.0ms).

#### Q30 [KG]: What are the primary threats to validity of this study?
**A:**
1. *Derived Service Times:* 1995 logs record bytes transferred, not CPU cycle counts.
2. *Homogeneous Cores:* Assumes uniform execution speed without NUMA latency or thermal throttling.
3. *Network Transport:* Assumes idealized instantaneous packet arrival without modeling TCP slow start or packet drops.

---

### Section 6: AST Sandboxing & Systems Security

#### Q31 [KG]: Why is Python's `eval()` or `exec()` dangerous without sandboxing?
**A:** Unrestricted `eval()` allows executing arbitrary byte code. An attacker can access builtins via `__builtins__`, import `os` or `subprocess`, spawn reverse shells, inspect filesystem contents, or execute denial-of-service fork bombs.

#### Q32 [KG]: How does NetSim-RT's AST validator secure custom policy code?
**A:** Before compilation, the code is parsed into an Abstract Syntax Tree (`ast.parse`). A custom `NodeVisitor` walks every node and enforces a strict whitelist:
- Allowed: Basic mathematical operations, list/dict comprehensions, conditional branches, comparisons.
- Prohibited: `Import`, `ImportFrom`, `Call` to unapproved identifiers, attribute access to dunder attributes (`__subclasses__`, `__class__`), and file I/O.

#### Q33 [MM]: What OS-level enforcement mechanisms backup the AST validator?
**A:** NetSim-RT runs custom policies in an isolated process using Linux kernel resource limits (`resource.setrlimit`):
- `RLIMIT_CPU = 2.0s`: Automatically sends `SIGXCPU` if policy code loops infinitely.
- `RLIMIT_AS = 256MB`: Caps virtual memory address space to prevent out-of-memory memory exhaustion.

#### Q34 [BR]: What happens if a user submits malicious or buggy custom policy code?
**A:** The engine implements a three-tier fail-safe:
1. Syntax/AST violations raise an immediate 400 Bad Request with a clear security error.
2. Execution timeouts or exceptions during simulation are caught.
3. The engine automatically logs the failure and falls back to baseline FCFS, preventing server crashes.

---

### Section 7: Software Engineering, Caching & Scalability

#### Q35 [KG]: Why did we choose DuckDB for result caching?
**A:** DuckDB is an in-process, embeddable columnar analytical engine. Unlike SQLite, DuckDB is optimized for vectorized aggregation over analytical datasets, reads and writes Parquet natively, supports zero-copy Arrow memory sharing, and executes sub-millisecond queries for precomputed presets.

#### Q36 [MM]: How does NetSim-RT achieve 333,000+ events per second in pure Python?
**A:**
1. Event queue is implemented with Python's optimized C-heap (`heapq`).
2. Heavy numpy vectorization is used for metric calculations (percentiles, histograms).
3. Fast integer bit-masking and pre-allocated object slots minimize garbage collection churn during the event loop.

#### Q37 [BR]: Why did external port 3507 initially fail to reach sys1, and how was it solved?
**A:** The sys1 environment runs inside an isolated container with NAT port redirection. Decisive network probing revealed that external port 3507 maps to internal container port 3000 (following an $X507 \to X000$ container port mapping scheme). Re-binding uvicorn to `0.0.0.0:3000` made the app directly reachable at `http://10.1.75.40:3507`.

#### Q38 [KG]: How does the event-driven simulator advance time compared to time-stepped simulation?
**A:** Time-stepped simulation increments clock by fixed $\Delta t$, wasting CPU cycles when no events occur and losing precision within intervals. Discrete-Event Simulation (DES) maintains a timestamped priority queue of state change events (arrivals, completions, timeouts) and advances the clock instantaneously to the next scheduled event time $t_{next}$.

#### Q39 [MM]: How do we ensure zero synthetic data is present in our evaluation?
**A:** Our ingestion pipeline (`scripts/fetch_data.py`) downloads raw historical logs from the Internet Traffic Archive (ITA) and Azure Public Dataset, validates SHA256 checksums, and compiles them directly into Apache Parquet. Synthetic generation is isolated strictly inside `tests/` for unit testing closed forms.

#### Q40 [BR]: How can NetSim-RT be scaled to simulate millions of requests across multi-datacenter topologies?
**A:** By partitioning the simulation space using Conservative or Optimistic Parallel Discrete Event Simulation (PDES) frameworks (e.g., Chandy-Misra-Bryant null-message algorithm), where independent cluster queues advance on separate CPU cores synchronized via minimal lookahead message queues.

---

### Section 8: Real System Emulation & Simulation Validation

#### Q41 [KG]: How does our real-system emulation testbed validate the simulator?
**A:** We created an emulation harness (`emulation/server.py` and `emulation/loadgen.py`) deployed on sys1 that mirrors the simulator's exact structural model: an asynchronous FastAPI front process with a central FIFO queue feeding $c=4$ dedicated multi-process workers. Each worker burns CPU cycles on physical cores using `time.perf_counter()` busy-spinning for the exact empirical service time derived from the trace. Under identical replayed arrival schedules, we measure real response metrics and directly benchmark them against the DES.

#### Q42 [MM]: How does time-dilation preserve queueing utilization mathematically?
**A:** Time dilation scales both inter-arrival times $\Delta t_i$ and service times $s_i$ by the exact same factor $D$ ($s' = D \cdot s$, $\Delta t' = D \cdot \Delta t$). Since arrival rate scales as $\lambda' = \lambda / D$ and service capacity scales as $\mu' = \mu / D$, the resulting traffic intensity $\rho' = \lambda' / (c \cdot \mu') = \lambda / (c \cdot \mu) = \rho$ remains strictly invariant. This allows testing heavy queueing congestion while throttling network I/O below ~300 req/s to prevent loopback socket buffer saturation.

#### Q43 [BR]: Why did we isolate worker processes and the load generator using CPU taskset affinity?
**A:** In a multi-core server (sys1 has 120 cores), CPU-bound busy-spinning workers can starve the asynchronous load generator and OS network interrupt handlers if scheduled onto shared physical cores. We pinned the 4 worker processes to cores 0-3 via `os.sched_setaffinity` and isolated the asynchronous load generator onto cores 8-15, eliminating CPU contention and guaranteeing that recorded timing variances reflect real system queueing dynamics rather than loadgen scheduling starvation.

#### Q44 [KG]: What are the overall MAPE numbers between emulation and simulation?
**A:** Throughput MAPE is 41.29% across all 6 utilization levels ($\rho \in [0.30, 1.08]$), tracking tightly at moderate load ($\rho \le 0.85$, throughput error 17.8%-37.5%). Latency MAPE is 67.51% for p50 and 124.06% for p99, reflecting the fundamental physical distinction between idealized zero-overhead DES discrete logic and Linux OS kernel scheduling/preemption.

#### Q45 [MM]: Why does real p99 latency show discrepancy at very light load ($\rho < 0.6$)?
**A:** Discrete-event simulation assumes instantaneous request ingestion, zero network transit time, and instantaneous dispatch. In the real running system, HTTP request framing, TCP loopback handshake/socket traversal, Python string serialization, and multiprocessing IPC queue primitives impose a physical baseline latency floor of ~1.0-1.8 ms. At low utilization where queueing delay is near zero, this constant runtime overhead constitutes the majority of measured latency.

#### Q46 [BR]: Why does real latency explode faster than simulation near saturation ($\rho \ge 0.95$)?
**A:** In DES, workers switch contexts with zero latency, and timer events fire with infinite precision. In the real system under saturation, Linux Completely Fair Scheduler (CFS) preemption, thread context switches, Python GIL contention in the event loop, and asynchronous socket backpressure cause head-of-line blocking and cascading delays. Requests queue up past client timeouts, triggering real-world drop-tail congestion collapse.
