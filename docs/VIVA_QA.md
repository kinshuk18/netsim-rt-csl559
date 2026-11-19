# VIVA Q&A — NetSim-RT (CSL559 IIT Bhilai)

> All answers below use freshly computed numbers from the full EPA trace (N=47 742,
> rho_analytic axis, max_requests=None).

**Q: What is the formal definition of the knee point and why does knee < breaking hold?**
A: **knee = max curvature of p99(rho) on rho<=rho_break, because beyond it p99 plateaus at the 30 s client timeout; knee<breaking holds by construction.** The search for the knee is mathematically bounded to `knee_search_range = [rho_min, rho_break]` (specifically `[0.0200, 0.3847]`). Searching beyond `rho_break` would conflate organic queue growth curvature with artificial flattening caused by the 30 s client timeout ceiling.

**Q: Why is the inflection point (max-slope point) greater than the breaking point?**
A: **Inflection (max-slope point, rho=0.458) > breaking (rho=0.385) occurs due to the 30 s client timeout plateau (not drop-tail queue-capacity clipping).** Past breaking (rho=0.385, p99=958.6 ms), the queue rapidly fills and tail latency accelerates steeply through rho=0.458 (p99=6711.4 ms) and rho=0.545 (p99=22463 ms) before plateauing at rho=0.648 (p99=30002 ms) because requests unserved after 30 s time out in queue before dispatch and are excluded from completed latency metrics (queue capacity was never reached, drop_rate=0.0). This timeout plateau creates an upper bound of wait (<30 s) + service (~2 ms), giving the p99(rho) trajectory a sigmoidal profile where the maximum slope (inflection point) falls between the onset of breakdown and the 30 s timeout plateau. Citing the measured values: **6711 ms (rho=0.458) → 22463 ms (rho=0.545) → 30002 ms (rho=0.648)**.

**Q: Why does the system break at only ~38% utilization?**
A: Heavy-tail P-K effect combined with arrival burstiness. cv²=2.93 means E[S²]=E[S]²×(1+cv²)=3.93× higher than exponential M/M/1. P-K theoretical mean wait at ρ=0.385 is **8.94 ms**, while simulated mean wait is **112.25 ms** (simulated mean latency is **119.53 ms**). The top-1% long jobs stall the FCFS queue, and short-term 60s arrival bursts push instantaneous load to ρ_burst = 1.67, pushing p99 to **958.6 ms** (> 500 ms SLO). Breaking point: **ρ=0.385 (FCFS), ρ=0.458 (SJF)**.

**Q: How does SJF shift the knee?**
A: SJF prioritises short jobs → drains queue faster for the median request → p99 of short-job class improves → knee shifts right. Measured:
- FCFS knee: ρ=0.272, offered=37.3 req/s, mult=67.5×, p99=285.8 ms
- SJF knee: ρ=0.323, offered=44.4 req/s, mult=80.4×, p99=252.1 ms
SJF shifts the knee right by **Δρ=0.051** (19% more load capacity before onset of degradation).

**Q: What is ρ at breaking?**
A: ρ=0.385 (c=1, FCFS); ρ=0.458 (c=1, SJF). Breaking = lowest rho where p99 > 500 ms SLO. Root causes: cv²=2.93 (P-K numerator 3.93× M/M/1) and 60s arrival burstiness (PMR_60=4.34x).

**Q: Why FCFS vs SJF spread at heavy load?**
A: At high ρ, SJF starves large requests in favour of small ones — p99 diverges across job classes. At ρ≈0.6, SJF p99 is 3031 ms while MLFQ p99 is 65608 ms and RR is 64635 ms. Under FCFS, heavy-tail service is FIFO-shared; under MLFQ/RR, preemption and time-slicing amplify tail delays.

**Q: Why does MLFQ p99 reach 65.6 s while FCFS p99 plateaus at ~30.0 s under the same 30 s client timeout? Is it a bug?**
A: **Not a bug — it is an inherent consequence of time-slicing vs queue timeout semantics.** Under FCFS and SJF, requests wait non-preemptively in queue; requests unserved after 30 s time out (`start_time < 0`), are flagged `timed_out=True`, and discarded without completing (715 timed out in FCFS, 765 in SJF at rho=0.6). Because timed-out requests are excluded from latency metrics, completed FCFS latency is artificially capped at wait (<30 s) + service (~2 ms) = 30002 ms. Under MLFQ (and RR), every incoming request enters Q0 and receives its initial 10 ms quantum within 30 s (`start_time >= 0`), which permanently prevents client timeout. Long requests are demoted to Q1 (20 ms) and Q2 (40 ms) and face queuing delay behind new Q0 arrivals and periodic boosts (every 2.0 s), but they complete with remaining service fully preserved (0 timed out, 47742/47742 completed). Measured at rho=0.6 (full EPA, c=1):
- **FCFS**: p50=5677.5 ms, p95=29705.6 ms, p99=29991.3 ms, max=30281.1 ms, completed=46941, timed_out=715, mean slowdown Q1=4363.3, Q4=1448.9.
- **RR**: p50=3475.4 ms, p95=35546.6 ms, p99=64642.2 ms, max=187066.1 ms, completed=47742, timed_out=0, mean slowdown Q1=2460.3, Q4=1116.7.
- **SJF**: p50=16.6 ms, p95=143.3 ms, p99=3003.5 ms, max=29743.6 ms, completed=46977, timed_out=765, mean slowdown Q1=5.7, Q4=19.9.
- **MLFQ**: p50=2971.2 ms, p95=36709.6 ms, p99=65606.4 ms, max=187792.1 ms, completed=47742, timed_out=0, mean slowdown Q1=2329.7, Q4=1088.5.
MLFQ accelerates short jobs (Q1 slowdown 2329.7 vs 4363.3 FCFS, median latency 2971.2 ms vs 5677.5 ms FCFS), but demoted long jobs endure full queue delays across quantum rounds without timing out, extending tail completion latency to 65.6 s (p99) and 187.8 s (max).

**Q: What is the P-K formula and what does each term mean?**
A: E[W] = ρ·E[S]·(1+cv²) / [2·(1−ρ)].
- E[W]: mean queue wait
- ρ = λ·E[S]/c: traffic intensity
- cv²: squared coefficient of variation of service time (= 2.93 on EPA, heavy tail)
- (1+cv²) factor: amplifies wait for heavy-tailed workloads vs M/M/1

**Q: How is Jain's fairness index computed, and why does RR rank highest / SJF/SRTF lowest?**
A: Jain = (Σxᵢ)² / (n·Σxᵢ²) applied to the per-request **slowdown vector** (slowdownᵢ = latencyᵢ / service_timeᵢ, floored at 1.0). See engine/simulator.py L465–470.
- RR allocates equal time quanta → all requests slow by roughly the same factor → uniform slowdown distribution → high Jain.
- FCFS is service-time-blind; short jobs queued behind long ones get high slowdown.
- SJF/SRTF systematically delay large requests: small jobs → slowdown ≈ 1; large jobs → slowdown ≫ 1 → high variance → Jain as low as 0.057–0.066 (SRTF).

**Q: How does downtime injection work in NetSim-RT?**
A: SimulationConfig accepts server_downtime_start_s / server_downtime_end_s (sim time). During downtime, requests queue; servers go idle. At recovery, backlog drains. Injected at sim_time=17.3 s (=600 s trace / 34.7× mult) with 2-min trace downtime. FCFS peak_backlog=305 req, drain_time=2.03 s.

**Q: What causes retry storms and was metastable collapse observed?**
A: Under overload, timeouts re-enter queue with exponential backoff. Amplification reaches **2.860x** at rho=1.30. Goodput with retries remains >= goodput without retries across the rho grid (0.2–1.3); hence **no metastable collapse observed on this trace**.

**Q: What is the validation MAPE?**
A: Throughput MAPE=41.29%, p50 MAPE=67.51%, p99 MAPE=124.06%. DES accurately tracks throughput (queuing dynamics); real system adds ~1–1.8 ms HTTP/IPC latency floor at light load and CFS preemption tail divergence at saturation (ρ≥0.95).

**Q: Why is p99 MAPE 124%?**
A: At saturation (ρ≥0.95), Linux CFS scheduler preempts server threads causing tail latency 2–5× higher than DES. At light load (ρ<0.5), HTTP/IPC floor of ~1–2 ms dominates small service times. DES correctly ranks policies and predicts throughput; absolute tail latency requires OS-aware modelling. See LIMITATIONS.md.

**Q: Why is shootout p99 not comparable across policies?**
A: Timeouts apply only until service starts; RR/MLFQ start every request within one quantum so none time out and the worst finish at ~187 s; FCFS/SJF drop 715/765 unserved requests (1.5%/1.6%) and exclude them from p99.
