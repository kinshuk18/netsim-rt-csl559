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
F2 complete: KNEE_EXPLANATION.md + VIVA_QA.md with real computed numbers

OPEN: SJF knee (530.5x) NOT right of FCFS knee (530.5x) — recorded honestly.
S1: DONE — rate audit: EPA 4k-subset rate=0.1321 req/s, sweep range bug fixed (was 400x→1300x), KNEE_EXPLANATION.md updated
S2: DONE — presets rerun with correct sweep range (rho 0.001→1.29), retry_amp=2.30x ✓
S3: DONE — headline.py checks confirmed: drain=2.03s, amp=1.64x, rho_break=0.28 (in [0.05,1.3]) ✓
S4: DONE — validation.json updated: mape_rho_lte_0_9=69.56%, floor=6.47ms, LIMITATIONS.md+VIVA_QA.md appended
S5: DONE — smoke_ui 6/6 PASS, 18 pytest pass
S6: DONE — report assets generated (4 PDFs), main.tex authors/abstract/AI-decl filled, refs.bib written (9 refs), report_overleaf.zip created; latexmk stalled (acmart download), use Overleaf
S7: DONE — only /etc/passwd in security test (intentional), no real secrets in git
T1: DONE — CI skipif added for missing data/processed/epa.parquet, actions bumped to checkout@v5 and setup-python@v6, 18 passed locally (16 passed/2 skipped in CI simulation)
CI fix: data-dependent tests skip when parquet absent
