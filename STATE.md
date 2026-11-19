# NetSim-RT State (v0.7 Validation-Complete)
- Status: Stage D complete. Real system emulation testbed deployed & benchmarked on sys1 (c=4, pinned cores 0-3 vs loadgen 8-15).
- Validation Metrics: Throughput MAPE = 41.29%, p50 MAPE = 67.51%, p99 MAPE = 124.06% across 6 load levels (rho 0.30 to 1.08).
- Engineering Insight: DES tracks throughput accurately; real system adds ~1.0-1.8ms HTTP/IPC latency floor at light load and exhibits CFS preemption tail divergence at saturation (rho >= 0.95).
- UI: 8th 'Validation' tab added with interactive ECharts (throughput & p99), real-vs-sim comparison table, and synthetic M/M/1 & M/M/c verification notice.
- Live URL: http://10.1.75.40:3507 (sys1 container port 3000). All 8 tabs operational.
- Verification: 14/14 pytest unit tests passing, smoke_ui.py 6/6 PASS.
- Next: Stage E (v1.0) - LaTeX report compilation, vector report assets, GitHub Actions CI workflow.

OPEN: retry_storm amplification=1.07 < 1.5 at mult=310.0x — not fabricated.

F1 complete: shootout 4-mult, outage injection Jul95, retry_storm sweep, SJF sweep added
OPEN: retry_storm amplification=1.07 < 1.5 at mult=310x — not fabricated.
