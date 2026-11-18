# NetSim-RT State (v0.3)
- Done: Trace ingestion (6 traces parquet), closed-form M/M/c verification, scheduling policies (FCFS, SJF, SRTF, RR, Priority, MLFQ, EDF, WFQ, PS), load balancers (central, RR, random, JSQ, power-of-two), admission control (none, drop-tail, token-bucket), client timeout + retry-with-backoff, 8 pytest tests passing.
- Next: S1.3 sweep engine with KneeLocator / inflection / breaking point, S1.4 presets precomputation, S1.5 custom policy sandbox.
- How to run:
  - Local tests: `.venv/bin/pytest tests/ -q`
  - Local server: `.venv/bin/uvicorn server.main:app --port 8000`
  - Sys1 SSH: `ssh -p 2507 student@10.1.75.40`
- Known gaps: Frontend UI, Sweep API, Custom Policy sandbox AST execution, Sys1 deployment.
