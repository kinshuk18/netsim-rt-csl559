# NetSim-RT State (v0.5)
- Done: Engine completion with load balancing (Central, RR, JSQ, SQ2), admission (None, Drop-tail, Token-bucket), retries with backoff; 25-point log load sweep with KneeLocator, Inflection (d2 sign change), and Breaking point; 6 programmatic presets precomputed; custom policy AST sandbox + setrlimit + FCFS fallback; no-build vanilla dark frontend with vendored ECharts; sys1 deployment on port 3507 with scripts/deploy.sh; 14 pytest unit tests passing.
- Next: Stage 2 - Emulation testbed (S2.1), README.md (S2.2), docs (S2.3), Report LaTeX & assets (S2.4), CI workflow (S2.5).
- How to run:
  - Local tests: `.venv/bin/pytest tests/ -q`
  - Local server: `.venv/bin/uvicorn server.main:app --port 3507`
  - Demo (local fish): `ssh -N -f -L 3507:localhost:3507 -p 2507 student@10.1.75.40; and xdg-open http://localhost:3507`
  - Sys1 restart (remote): `bash scripts/restart_demo.sh`
- Known gaps: Stage 2 report generation, real emulation benchmark, and documentation assets.
