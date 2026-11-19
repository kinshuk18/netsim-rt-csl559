# NetSim-RT Submission & Demonstration Checklist

> **Course:** CSL559 - Computer Systems Design  
> **Course Project:** NetSim-RT: Trace-Driven Real-Traffic Simulator & Policy Benchmark  
> **Submission Deadline:** 3 Dec 2026, 11:59 PM IST  
> **Panel Demonstration:** Friday, 20 Nov 2026, 11:45 AM IST  
> **Authors:** Kinshuk Gupta (12341190), Maloth Madhu (12341370), Bhukya Raju (12340520)

---

## 1. Submission Deliverables Summary

- [x] **Project Repository URL:** https://github.com/kinshuk-gupta/NetSim-RT *(or course submission repository)*
- [x] **Live Front-End Application URL:** [http://10.1.75.40:3507](http://10.1.75.40:3507)
  > **Campus Network Reachability Note:** The IP `10.1.75.40` is hosted on the internal IIT Bhilai campus LAN (`10.x.x.x`). To access from outside campus, connect via institute VPN or establish an SSH SOCKS/port-forward tunnel:
  > ```bash
  > ssh -N -f -L 3607:localhost:3000 -p 2507 student@10.1.75.40
  > # Then open http://localhost:3607 in your local browser
  > ```
- [ ] **Demonstration Video URL (YouTube):** `[YOUTUBE LINK PLACEHOLDER - TO BE RECORDED & UPLOADED]` (Target: <= 5 minutes, 1080p60, high-res UI walkthrough adhering to `docs/DEMO_SCRIPT.md`).
- [ ] **Final Project Report (PDF):** Generated from `report/main.tex` adhering to the ACM SIGPLAN / course standard template.

---

## 2. Laptop Pre-Demo Checklist (Primary Presentation Machine)

- [ ] **Local Environment Verification:**
  ```bash
  cd "Real Traffic Simulator Project"
  .venv/bin/pytest tests/ -q
  # Ensure all 14 tests pass
  ```
- [ ] **Local Web App Ready on Laptop:**
  ```bash
  bash scripts/demo_local.sh
  # Verifies local binding at http://127.0.0.1:3507
  ```
- [ ] **Browser Prepared:**
  - Chrome / Chromium opened to `http://127.0.0.1:3507` (primary) and `http://10.1.75.40:3507` (backup sys1).
  - Zoom set to 100% or 110% for crisp projector rendering.
  - Browser console open (`F12`) to verify zero runtime JavaScript errors.
- [ ] **Display & Projection:**
  - HDMI / Type-C dongle tested.
  - Screen resolution set to 1920x1080.
  - Dark mode verified for contrast under lecture hall lighting.

---

## 3. Remote Backup Verification (sys1 Server)

- [ ] **SSH Connectivity Verified:**
  ```bash
  ssh -p 2507 student@10.1.75.40 'echo SSH_OK'
  ```
- [ ] **Remote Process Health Check:**
  ```bash
  curl -s http://10.1.75.40:3507/api/health
  # Expected: {"status":"healthy"}
  ```
- [ ] **Fast Remote Restart Command Tested:**
  ```bash
  bash scripts/restart_demo.sh
  ```

---

## 4. Viva Presentation Readiness

- [ ] **Role Allocation Agreed:**
  - **Kinshuk Gupta:** Problem formulation, systems architecture, queueing theory, AST security sandbox.
  - **Maloth Madhu:** Phase transitions (Knee, Inflection, Breaking), load sweep, MLFQ/SRTF dynamics.
  - **Bhukya Raju:** Multi-policy shootout, fairness metrics (Jain's index), Hurricane Erin outage, retry storms.
- [ ] **Key Numbers Memorized from `results/headline.json`:**
  - Knee: 69.7x load multiplier, 8.61 req/s, $\rho = 0.065$, $p99 = 81.8\text{ms}$.
  - Inflection: 114.8x load multiplier, 13.62 req/s, $\rho = 0.102$, $p99 = 199.1\text{ms}$.
  - Breaking: 311.6x load multiplier, 31.46 req/s, $\rho = 0.237$, $p99 = 500.4\text{ms}$ (SLO breach).
  - Shootout: FCFS/SJF optimal tail ($40.0\text{ms}$), Round Robin fair ($J = 0.899$), Priority unfair to browse ($J = 0.589$).
  - Simulation Speed: 333,526 events/second.

## v1.0 Final Status (S6e update)
- Live URL: http://10.1.75.40:3507 (working, 8 tabs, smoke_ui 6/6)
- Video link: [PLACEHOLDER - TEAM TO ADD before submission]
- v0.8 tag: set
- v1.0 tag: set
- 18 pytest tests: PASS
- report_overleaf.zip: generated for Overleaf compilation
