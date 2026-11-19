# Knee Point Explanation — NetSim-RT

> [!IMPORTANT]
> All numbers below are freshly computed from the full EPA trace (N=47 742 requests,
> span=86 382 s) using analytic rho (R2) and the updated sweep (R3).  
> No old claims carried forward.

## Queueing Parameters (EPA trace, c=1, FCFS)

| Symbol | Value | Meaning |
|--------|-------|---------|
| λ (lam) | 0.552685 req/s | Arrival rate from full trace (N/span) |
| E[S] | 7.279 ms | Mean service time (analytic, from trace) |
| E[S²] | 208.19 μs² | Second moment of service time |
| cv² | 2.9295 | Squared coefficient of variation (heavy tail) |
| ρ_knee | 0.2717 | Analytic utilization at knee (c=1 FCFS) |
| ρ_knee (SJF) | 0.3233 | SJF knee — higher than FCFS (SJF shifts right ✓) |
| ρ_breaking | 0.3847 | FCFS: lowest rho with p99 > 500 ms SLO |
| ρ_breaking (SJF) | 0.4578 | SJF breaking — higher than FCFS (SJF delays collapse ✓) |

## Pollaczek-Khinchine (P-K) Mean Wait Formula

For M/G/1 queue:

```
E[W] = ρ · E[S] · (1 + cv²) / [2 · (1 − ρ)]
```

**At the knee** (ρ = 0.2717, FCFS):
- P-K predicted mean wait = **5.335 ms**
- Simulator measured p99 = **285.8 ms**

**At the breaking point** (ρ = 0.3847, FCFS):
- P-K predicted mean wait = **8.943 ms**
- Simulator measured p99 = **958.6 ms**

> [!NOTE]
> P-K gives mean wait; p99 is 50–100× higher due to heavy-tailed service times
> (cv² = 2.93). A single long job (HTTP large file) stalls the queue while short
> requests pile up. The tail is amplified, not the mean.

## Why System Breaks at Only ~38% Utilization

With **cv² = 2.93**, the numerator of P-K is **(1 + cv²) = 3.93×** larger than
M/M/1. Even at ρ = 0.38, one heavy request (top 1% of service times) adds
50–200 ms of wait for all queued short jobs — which collectively breaches p99 > 500 ms.

```
E[S²] = E[S]² × (1 + cv²) = (7.28 ms)² × 3.93 = 208.2 μs²
```

## How SJF Shifts the Knee

SJF prioritises short jobs → drains queue faster → mean wait for the median
request improves significantly. Measured results:

- **FCFS knee**: ρ = 0.272 (offered 37.3 req/s, mult 67.5×, p99 = 285.8 ms)
- **SJF knee**: ρ = 0.323 (offered 44.4 req/s, mult 80.4×, p99 = 252.1 ms)
- **FCFS breaking**: ρ = 0.385 (p99 = 958.6 ms)
- **SJF breaking**: ρ = 0.458 (p99 = 1 067.3 ms)

SJF shifts **both** the knee and the breaking point to higher utilization,
confirming the theoretical advantage of size-aware scheduling under heavy tails.

## How Jain's Fairness Index Is Computed

```python
# Engine code: engine/simulator.py lines 465–470
slowdowns = [max(1.0, latency / max(0.0001, service_time))
             for r in completed_requests]
# Jain's formula applied to the slowdown vector:
sum_s  = sum(slowdowns)
sum_sq = sum(s**2 for s in slowdowns)
n      = len(slowdowns)
jain   = sum_s**2 / (n * sum_sq)   # ∈ (0, 1]
```

**Vector**: per-request slowdown = latency / service_time (≥ 1.0).  
**Jain's index** = (Σxᵢ)² / (n · Σxᵢ²), where xᵢ = slowdownᵢ.

| Policy | Jain | Why |
|--------|------|-----|
| RR | 0.674 | Shares server in fixed quanta → all requests slow by roughly equal factor |
| FCFS | ~0.5 | Service-time-blind; short jobs queued behind long ones get high slowdown |
| SJF | ~0.4 | Favours short jobs → they get low slowdown; long jobs get very high slowdown → unfair |
| SRTF | 0.057 | Preempts long jobs aggressively → extreme slowdown for large requests → worst fairness |

> [!TIP]
> High Jain ≠ good tail latency. RR is fairest by slowdown but has worse p99 than FCFS
> at high load because time-slicing wastes context-switch overhead and prevents long-job
> completion.

## "Break at X% utilization" — Authoritative Answer

> **FCFS on EPA trace (c=1) breaks at ρ = 0.385 (38.5% utilization).**  
> This is caused by cv² = 2.93 (heavy-tailed service times), not low server capacity.  
> The P-K numerator is 3.93× larger than M/M/1, making mean wait explode even at moderate load.  
> SJF delays collapse to ρ = 0.458 (45.8%) by prioritising short jobs.

## VIVA QA

**Q: How is Jain's fairness index computed, and why does RR rank highest / SJF lowest?**

A: Jain's index = (Σxᵢ)² / (n · Σxᵢ²) applied to the per-request *slowdown*
vector (slowdown = latency / service_time, floored at 1.0).  
RR allocates equal time quanta, so every request's slowdown is proportional to
the number of requests it must share the server with — i.e., all requests are
slowed by the same factor, giving a uniform slowdown distribution and high Jain.  
SJF (and SRTF) systematically delay large requests in favour of small ones:
small requests get slowdown ≈ 1, large requests get slowdown ≫ 1, creating high
variance → low Jain index.

**Q: What is ρ at the knee and breaking point, and why does the system collapse so early?**

A: Knee at ρ = 0.272 (FCFS) / ρ = 0.323 (SJF). Breaking at ρ = 0.385 (FCFS) / ρ = 0.458 (SJF).  
Root cause: cv² = 2.93 on EPA service times. P-K mean wait = ρ·E[S]·(1+cv²)/[2(1−ρ)].  
With cv² = 2.93 the numerator is 3.93× that of M/M/1. At ρ = 0.38, P-K predicts
8.9 ms mean wait, but the top-1% long jobs add 200–500 ms of real wait, pushing p99 ≫ 500 ms.

**Q: Does SJF improve fairness?**

A: No. SJF worsens Jain fairness (SJF Jain ≈ 0.4 vs FCFS ≈ 0.5) because it
systematically disadvantages large requests. SJF improves *throughput stability*
and shifts the breaking point right (ρ_break = 0.458 vs 0.385).
