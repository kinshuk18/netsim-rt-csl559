# NetSim-RT Datasets & Workload Traces

All data in **NetSim-RT** originates strictly from verified, publicly available, real-world operational traces. Synthetic workloads are strictly disallowed in all simulation runs, results, and reports.

---

## 1. Trace Inventory & Provenance

| Trace Identifier | Source Organization | Period | Total Requests | Compression Format | Source URL / Repository |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **NASA-HTTP** | NASA Kennedy Space Center (KSC) | Jul 01 – Aug 31, 1995 | ~3,461,612 | `.gz` (gzip) | `http://ita.ee.lbl.gov/html/contrib/NASA-HTTP.html` |
| **ClarkNet-HTTP** | ClarkNet Commercial ISP | Aug 28 – Sep 10, 1995 | ~3,328,587 | `.gz` (gzip) | `http://ita.ee.lbl.gov/html/contrib/ClarkNet-HTTP.html` |
| **EPA-HTTP** | US Environmental Protection Agency | Aug 29 – Aug 30, 1995 | 47,748 | `.txt.Z` (compress) | `http://ita.ee.lbl.gov/html/contrib/EPA-HTTP.html` |
| **SDSC-HTTP** | San Diego Supercomputer Center | Aug 22 – Sep 11, 1995 | 28,338 | `.txt.Z` (compress) | `http://ita.ee.lbl.gov/html/contrib/SDSC-HTTP.html` |
| **Saskatchewan-HTTP** | University of Saskatchewan | Jun 01 – Dec 31, 1995 | ~2,408,625 | `.gz` (gzip) | `http://ita.ee.lbl.gov/html/contrib/Sask-HTTP.html` |
| **Azure Functions 2021** | Microsoft Azure Serverless | Jan 31 – Feb 14, 2021 | Sampled 1M+ | `.rar` (RAR5) | `https://github.com/Azure/AzurePublicDataset` |

---

## 2. License & Terms of Use

- **Internet Traffic Archive (ITA) Datasets** (NASA, ClarkNet, EPA, SDSC, Saskatchewan):
  - Collected and distributed through the Internet Traffic Archive sponsored by ACM SIGCOMM.
  - Freely redistributable for research, benchmarking, and educational evaluation with appropriate citation.
- **Microsoft Azure Public Dataset (Azure Functions 2021)**:
  - Licensed under the **Creative Commons Attribution 4.0 International (CC-BY 4.0)** license.
  - Requires citation of the SOSP 2021 paper: *Zhang et al., "Faster and Cheaper Serverless Computing on Harvested Resources", SOSP 2021*.

---

## 3. Academic Citations

1. **NASA & Workload Invariants**:
   > Martin F. Arlitt and Carey L. Williamson. 1996. *Web server workload characterization: the search for invariants*. In Proceedings of the 1996 ACM SIGMETRICS Conference on Measurement and Modeling of Computer Systems (SIGMETRICS '96), 126–137. DOI: 10.1145/233013.233034
2. **Azure Serverless Traces**:
   > Yanqi Zhang, Íñigo Goiri, Gohar Irfan Chaudhry, Rodrigo Fonseca, Sameh Elnikety, Christina Delimitrou, and Ricardo Bianchini. 2021. *Faster and cheaper serverless computing on harvested resources*. In Proceedings of the ACM SIGOPS 28th Symposium on Operating Systems Principles (SOSP '21), 724–739. DOI: 10.1145/3477132.3483580

---

## 4. Pipeline & Unified Parquet Schema

Raw log lines are parsed using DuckDB and PyArrow into unified, compressed Parquet files (`data/processed/<trace_name>.parquet`).

| Column | Type | Description |
| :--- | :--- | :--- |
| `ts` | `DOUBLE` | Normalized arrival timestamp in seconds from start of trace ($t_0 = 0.0$). |
| `host_hash` | `STRING` | 64-bit cryptographic hash of the client identifier (IP or hostname). |
| `class` | `STRING` | Request category: `'browse'` (static GETs: images, HTML) vs. `'book'` (dynamic POSTs, CGI, transactions). |
| `path_group` | `STRING` | Normalized endpoint cluster (e.g., `/images`, `/cgi-bin`, `/htbin`, `/pages`). |
| `bytes` | `INT64` | Transferred payload length in bytes (0 if error or missing). |
| `status` | `INT32` | Standard HTTP response code (e.g., 200, 302, 304, 404, 500). |
| `service_time_s` | `DOUBLE` | Ground-truth service time. For Azure: true duration. For ITA logs: calibrated $s_0(\text{class}) + \text{bytes} / B_{\text{eff}}$. |

---

## 5. Hurricane Erin Physical Outage Gap (NASA Trace)
- In the August 1995 NASA dataset, Hurricane Erin forced the shutdown of Kennedy Space Center servers.
- The log records an outage gap from **01 Aug 1995 14:52:01 UTC** until **03 Aug 1995 04:36:13 UTC** (~37.7 hours of zero requests).
- NetSim-RT leverages this real-world operational event to benchmark server backlog, queue buildup, and recovery dynamics under post-outage thundering-herd arrival surges.
