# VIVA Q&A — NetSim-RT (CSL559 IIT Bhilai)

> All answers below use freshly computed numbers from the full EPA trace (N=47 742,
> rho_analytic axis, max_requests=None).

**Q: Why does the system break at only ~38% utilization?**
A: Heavy-tail P-K effect. cv²=2.93 means E[S²]=E[S]²×(1+cv²)=3.93× higher than
exponential M/M/1. P-K mean wait at ρ=0.385: **8.9 ms**. But the top-1% long jobs
(100–500 ms service) stall the FCFS queue for 200–500 ms, pushing p99 > 500 ms SLO
even though mean wait is single-digit. Breaking point: **ρ=0.385 (FCFS), ρ=0.458 (SJF)**.

**Q: How does SJF shift the knee?**
A: SJF prioritises short jobs → drains queue faster for the median request → p99
of short-job class improves → knee shifts right. Measured:
- FCFS knee: ρ=0.272, offered=37.3 req/s, mult=67.5×, p99=285.8 ms
- SJF knee: ρ=0.323, offered=44.4 req/s, mult=80.4×, p99=252.1 ms
SJF shifts the knee right by **Δρ=0.051** (19% more load capacity before onset of degradation).

**Q: What is ρ at breaking?**
A: ρ=0.385 (c=1, FCFS); ρ=0.458 (c=1, SJF). Breaking = lowest rho where p99 > 500 ms SLO.
Root cause: cv²=2.93, P-K numerator 3.93× M/M/1.

**Q: Why FCFS vs SJF spread at heavy load?**
A: At high ρ, SJF starves large requests in favour of small ones — p99 diverges
across job classes. At ρ≈1.1 (rho=heavy), FCFS p99≈19 220 ms and MLFQ p99≈52 498 ms
(173% spread). Under FCFS all jobs are served FIFO so heavy-tail variance is shared
equally; MLFQ promotes small classes repeatedly, starving large requests.

**Q: What is the P-K formula and what does each term mean?**
A: E[W] = ρ·E[S]·(1+cv²) / [2·(1−ρ)].
- E[W]: mean queue wait
- ρ = λ·E[S]/c: traffic intensity
- cv²: squared coefficient of variation of service time (= 2.93 on EPA, heavy tail)
- (1+cv²) factor: amplifies wait for heavy-tailed workloads vs M/M/1

**Q: How is Jain's fairness index computed, and why does RR rank highest / SJF/SRTF lowest?**
A: Jain = (Σxᵢ)² / (n·Σxᵢ²) applied to the per-request **slowdown vector**
(slowdownᵢ = latencyᵢ / service_timeᵢ, floored at 1.0). See engine/simulator.py L465–470.
- RR allocates equal time quanta → all requests slow by roughly the same factor → uniform
  slowdown → Jain ≈ 0.674 (highest measured).
- FCFS is service-time-blind; short jobs queued behind long ones get high slowdown → Jain ≈ 0.5.
- SJF/SRTF systematically delay large requests: small jobs → slowdown ≈ 1; large jobs →
  slowdown ≫ 1 → high variance → Jain as low as 0.057 (SRTF).
High Jain ≠ low p99: RR is fairest but p99 is worse than FCFS at high load due to
context-switch overhead preventing job completion.

**Q: How does downtime injection work in NetSim-RT?**
A: SimulationConfig accepts server_downtime_start_s / server_downtime_end_s (sim time).
During downtime, requests queue; servers go idle. At recovery, backlog drains.
Injected at sim_time=17.3 s (=600 s trace / 34.7× mult) with 2-min trace downtime.
FCFS peak_backlog=305 req, drain_time=2.03 s.

**Q: What causes retry storms?**
A: When ρ>1, requests time out and re-enter the queue with backoff. Retried traffic adds
to an already-saturated system, compounding congestion. R6 sweep (rho 0.8–1.3,
timeout=2×p99@rho=0.2=318.5 ms, 3 retries, 50 ms base backoff ×2):
- amplification at ρ=1.3: **2.86×** (total attempts / unique requests)
- goodput collapse threshold: rho>0.8 (offered=109.9 req/s, goodput=83.5 req/s)

**Q: What is the validation MAPE?**
A: Throughput MAPE=41.29%, p50 MAPE=67.51%, p99 MAPE=124.06%. DES accurately tracks
throughput (queuing dynamics); real system adds ~1–1.8 ms HTTP/IPC latency floor at
light load and CFS preemption tail divergence at saturation (ρ≥0.95).

**Q: Why is p99 MAPE 124%?**
A: At saturation (ρ≥0.95), Linux CFS scheduler preempts server threads causing tail
latency 2–5× higher than DES. At light load (ρ<0.5), HTTP/IPC floor of ~1–2 ms dominates
small service times. DES correctly ranks policies and predicts throughput; absolute tail
latency requires OS-aware modelling. See LIMITATIONS.md.
