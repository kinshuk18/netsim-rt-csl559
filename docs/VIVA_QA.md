# VIVA Q&A — NetSim-RT (CSL559 IIT Bhilai)

**Q: Why does the system break at only ~24% utilization?**
A: Heavy-tail P-K effect — E[S²] term in Pollaczek-Khinchine formula; cv²=2.93 means E[S²]=E[S]²×(1+cv²)=3.93× higher than exponential, so queue blows up at low ρ. At ρ=0.237 the denominator (1−ρ) is still 0.763, but the numerator is already 3.93× inflated, causing p99 > 500 ms SLO.

**Q: How does SJF shift the knee?**
A: SJF prioritizes short jobs → drains queue faster → p99 of heavy jobs may worsen but mean wait improves → effective knee shifts right. Measured: FCFS knee at 69.7× (ρ=0.065), SJF knee at 242.8× (ρ=0.195) — a 3.5× shift in load capacity before degradation.

**Q: What is ρ at breaking?**
A: 0.237 (c=1 FCFS); ~0.646 (c=2, at 311.6× multiplier). Breaking occurs when p99 > 500 ms SLO target.

**Q: Why FCFS vs SJF spread at heavy load?**
A: At high ρ, SJF starves long jobs but completes short ones fast — p99 diverges between best and worst job classes. Under FCFS all jobs are served FIFO so variance is shared equally; under SJF short-job p99 improves dramatically but long-job p99 explodes.

**Q: What is the P-K formula and what does each term mean?**
A: E[W] = ρ·E[S]·(1+cv²) / [2·(1−ρ)]. E[W]=mean queue wait, ρ=traffic intensity λ·E[S]/c, cv²=variance/mean² of service time (heaviness). The (1+cv²) factor amplifies wait for heavy-tailed workloads.

**Q: How does downtime injection work in NetSim-RT?**
A: SimulationConfig accepts server_downtime_start_s / server_downtime_end_s (simulator time). During downtime, arriving requests queue; servers go idle. At recovery, the backlog drains. We inject at sim_time=17.3s (= 600s trace/34.7x mult) with 2-min trace downtime. FCFS peak_backlog=305 reqs, drain_time≈2s.

**Q: What causes retry storms?**
A: When server is overloaded (ρ>1), requests time out and re-enter the queue with backoff. At high offered load, retried traffic adds to already-saturated system, compounding congestion. Our sweep (mult 180–310×, timeout=2×baseline_p99) measured amplification=1.07× at the heaviest point — indicating the backoff strategy (50ms base, ×2 multiplier) is effective at limiting amplification even at ρ>1.

**Q: What is Jain's fairness index?**
A: J = (Σxᵢ)² / (n·Σxᵢ²) where xᵢ = slowdown (latency/service_time). J=1.0 means perfectly fair; lower values indicate certain requests are disproportionately penalized. FCFS typically has J>0.95; MLFQ and SJF show lower fairness at high load due to class differentiation.

**Q: What is the validation MAPE?**
A: Throughput MAPE=41.29%, p50 MAPE=67.51%, p99 MAPE=124.06%. DES accurately tracks throughput (queuing dynamics); real system adds ~1-1.8ms HTTP/IPC latency floor at light load and CFS preemption tail divergence at saturation (ρ≥0.95).

Q: Why is p99 MAPE 124%?
A: At saturation (ρ≥0.95), Linux CFS scheduler preempts server threads causing tail latency 2-5× higher than DES. At light load (ρ<0.5), HTTP/IPC floor of ~1-2ms dominates small service times. DES correctly ranks policies and predicts throughput (MAPE 41%), but absolute tail latency requires OS-aware modeling. This is documented honestly in LIMITATIONS.md.
