# NetSim-RT Assumptions & Network Architecture

## Port Mapping (sys1: 10.1.75.40)
- sys1 runs inside an isolated container/VM environment with NAT port forwarding:
  - External port `2507` -> Internal container port `22` (SSH)
  - External port `3507` -> Internal container port `3000` (FastAPI / NetSim-RT Web App)
  - External port `5507` -> Internal container port `5000`
- External port `3507` is directly reachable from the campus LAN (`http://10.1.75.40:3507`) when uvicorn binds to `0.0.0.0:3000`.
- SSH Tunnel Fallback: `ssh -N -f -L 3607:localhost:3000 -p 2507 student@10.1.75.40` accesses the app at `http://localhost:3607`.

## Trace Assumptions
- NASA-HTTP 1995 & WorldCup98 traces do not record per-request service time. Service time is derived from payload byte size via calibrated transfer model (`transmission_time = bytes / bandwidth + base_latency`), matching empirical HTTP/1.0 server dynamics (Arlitt & Williamson 1996).
- Synthetic data is strictly prohibited in real presets and evaluation; used only in isolated unit tests.
