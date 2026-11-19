# Knee Point Explanation — NetSim-RT

## Queueing Parameters (EPA trace, c=1 FCFS)

| Symbol | Value | Meaning |
|--------|-------|---------|
| E[S] | 7.5 ms | Mean service time |
| E[S²] | 221.06 μs² | Second moment of service time |
| cv² | 2.93 | Squared coefficient of variation (heavy tail) |
| λ_knee | 8.61 req/s | Offered load at knee point |
| ρ_knee | 0.0648 | Server utilization at knee |
| ρ_breaking | 0.237 | Utilization at SLO breach (p99 > 500 ms) |

## Pollaczek-Khinchine (P-K) Mean Wait Formula

For M/G/1 queue:

```
E[W] = ρ · E[S] · (1 + cv²) / [2 · (1 − ρ)]
```

**At the knee** (ρ = 0.0648):
- P-K predicted wait = **1.02 ms**
- P-K p99 approximation (×4.6) = **4.7 ms**
- Simulator measured p99 = **81.75 ms**

> [!NOTE]
> The gap between P-K prediction and simulation arises because P-K gives the
> *mean wait*, not p99. For heavy-tailed service times (cv²=2.93), p99 can be
> 20–50× the mean wait due to occasional very long jobs.

## Why System Breaks at Only ~24% Utilization

The M/G/1 queue blows up because the E[S²] term dominates at high cv²:

```
E[S²] = E[S]² · (1 + cv²) = (7.5 ms)² × 3.93 = 221 μs²
```

With **cv² = 2.93** (vs. 1.0 for exponential), the numerator of P-K is
**3.93×** larger than it would be for M/M/1. Even at ρ = 0.237, the queue
length diverges because a single heavy tail job blocks the server for 50–200 ms
while short jobs pile up.

**ρ at breaking point: 0.237 (c=1 FCFS); ~0.646 (c=2, 311.6×)**

## How SJF Shifts the Knee

SJF prioritizes short jobs → drains queue faster → mean wait improves for the
majority class. The effective knee shifts right: **SJF knee at 242.8× (ρ=0.195)
vs FCFS knee at 69.7× (ρ=0.065)**. However, p99 for the longest jobs may
worsen under SJF due to starvation at high load.
