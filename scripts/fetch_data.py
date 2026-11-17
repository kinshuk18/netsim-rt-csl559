#!/usr/bin/env python3
"""
NetSim-RT Data Fetch & Ingestion Pipeline
CSL559 Computer Systems Design - IIT Bhilai

Fetches, verifies, and transforms real-world HTTP and serverless operational traces
into unified, high-performance Apache Parquet tables and precomputes statistical
summaries for the Dataset Explorer.

Unified Schema:
- ts: float64 (arrival timestamp in seconds from trace start)
- host_hash: string (anonymized 16-hex character hash of client)
- class: string ('browse' | 'book')
- path_group: string (top-level directory or logical endpoint group)
- bytes: int64 (payload size in bytes)
- status: int32 (HTTP status code or simulated 200)
- service_time_s: float64 (ground-truth or calibrated service duration in seconds)
"""

import os
import sys
import re
import gzip
import subprocess
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# Bandwidth calibration for ITA traces: 10 MB/s effective I/O bandwidth
EFFECTIVE_BANDWIDTH_BPS = 10 * 1024 * 1024
# Base processing overheads (calibrated against sys1 testbed)
BASE_OVERHEAD_BROWSE_S = 0.0025  # 2.5 ms
BASE_OVERHEAD_BOOK_S = 0.0350    # 35.0 ms

MONTH_MAP = {
    'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
    'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
}

def ensure_dirs(base_dir: Path):
    raw_dir = base_dir / "raw"
    proc_dir = base_dir / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir, proc_dir

def categorize_request(path: str, method: str = "GET") -> Tuple[str, str]:
    """Categorize request into 'browse' vs 'book' and extract path_group."""
    p_lower = path.lower()
    m_upper = method.upper()
    
    is_book = (
        m_upper in ("POST", "PUT", "DELETE") or
        "/cgi-bin/" in p_lower or
        "/htbin/" in p_lower or
        ".cgi" in p_lower or
        ".pl" in p_lower or
        "book" in p_lower or
        "order" in p_lower or
        "cart" in p_lower or
        "login" in p_lower or
        "admin" in p_lower or
        "search" in p_lower
    )
    req_class = "book" if is_book else "browse"
    
    # Path group
    parts = [part for part in path.split('?')[0].split('/') if part]
    if not parts:
        path_group = "/"
    elif len(parts) == 1:
        path_group = f"/{parts[0]}"
    else:
        path_group = f"/{parts[0]}/{parts[1]}"
        
    return req_class, path_group

def parse_clf_date(date_str: str) -> float:
    """Parse Common Log Format timestamp: 01/Jul/1995:00:00:01 -0400."""
    try:
        parts = date_str.split()[0]
        day = int(parts[0:2])
        mon = MONTH_MAP[parts[3:6]]
        year = int(parts[7:11])
        hour = int(parts[12:14])
        minute = int(parts[15:17])
        sec = int(parts[18:20])
        dt = datetime(year, mon, day, hour, minute, sec)
        return dt.timestamp()
    except Exception:
        return 0.0

def parse_epa_date(date_str: str) -> float:
    """Parse EPA timestamp: [29:23:53:25] (Aug 1995)."""
    try:
        clean = date_str.strip("[]")
        day, hr, mn, sc = map(int, clean.split(":"))
        dt = datetime(1995, 8, day, hr, mn, sc)
        return dt.timestamp()
    except Exception:
        return 0.0

def parse_sdsc_date(date_str: str) -> float:
    """Parse SDSC timestamp: Tue Aug 22 00:00:00 1995."""
    try:
        parts = date_str.strip().split()
        mon = MONTH_MAP[parts[1]]
        day = int(parts[2])
        hr, mn, sc = map(int, parts[3].split(":"))
        year = int(parts[4])
        dt = datetime(year, mon, day, hr, mn, sc)
        return dt.timestamp()
    except Exception:
        return 0.0

def compute_hurst(ts_counts: np.ndarray) -> float:
    """
    Estimate Hurst exponent using Aggregated Variance method.
    Var(X^(m)) ~ m^(2H - 2)
    """
    if len(ts_counts) < 300:
        return 0.50
    m_values = [2, 4, 8, 16, 32, 64, 128, 256]
    variances = []
    valid_m = []
    
    for m in m_values:
        n_blocks = len(ts_counts) // m
        if n_blocks < 8:
            continue
        blocks = ts_counts[:n_blocks * m].reshape((n_blocks, m))
        block_means = blocks.mean(axis=1)
        var = np.var(block_means)
        if var > 1e-12:
            variances.append(var)
            valid_m.append(m)
            
    if len(valid_m) < 3:
        return 0.50
        
    log_m = np.log10(valid_m)
    log_var = np.log10(variances)
    slope, _ = np.polyfit(log_m, log_var, 1)
    h = (slope + 2.0) / 2.0
    return float(np.clip(h, 0.45, 0.98))

def compute_idc(ts_counts: np.ndarray) -> float:
    """Index of Dispersion for Counts: Var(N) / Mean(N)."""
    mean_val = np.mean(ts_counts)
    if mean_val < 1e-9:
        return 1.0
    return float(np.var(ts_counts) / mean_val)

def generate_metadata_summary(trace_name: str, df: pd.DataFrame, outage_window: Tuple[float, float] = None) -> Dict[str, Any]:
    """Compute rich metrics for Dataset Explorer."""
    total_reqs = int(len(df))
    if total_reqs == 0:
        return {"trace_name": trace_name, "total_requests": 0}
        
    duration_s = float(df['ts'].max() - df['ts'].min())
    avg_rate = float(total_reqs / duration_s) if duration_s > 0 else 0.0
    
    duration_int = int(np.ceil(duration_s)) + 1
    bin_size = max(1, duration_int // 1000)
    num_bins = max(10, duration_int // bin_size)
    counts, _ = np.histogram(df['ts'].values, bins=num_bins)
    
    rates = counts / float(bin_size)
    p50_rate = float(np.percentile(rates, 50))
    p95_rate = float(np.percentile(rates, 95))
    p99_rate = float(np.percentile(rates, 99))
    max_rate = float(np.max(rates))
    
    hurst = compute_hurst(counts)
    idc = compute_idc(counts)
    
    bytes_arr = df['bytes'].values
    size_dist = {
        'min': int(np.min(bytes_arr)),
        'p25': float(np.percentile(bytes_arr, 25)),
        'p50': float(np.percentile(bytes_arr, 50)),
        'p75': float(np.percentile(bytes_arr, 75)),
        'p90': float(np.percentile(bytes_arr, 90)),
        'p99': float(np.percentile(bytes_arr, 99)),
        'max': int(np.max(bytes_arr)),
        'mean': float(np.mean(bytes_arr))
    }
    
    st_arr = df['service_time_s'].values
    st_dist = {
        'p50_ms': float(np.percentile(st_arr, 50) * 1000.0),
        'p90_ms': float(np.percentile(st_arr, 90) * 1000.0),
        'p95_ms': float(np.percentile(st_arr, 95) * 1000.0),
        'p99_ms': float(np.percentile(st_arr, 99) * 1000.0),
        'max_ms': float(np.max(st_arr) * 1000.0),
        'mean_ms': float(np.mean(st_arr) * 1000.0)
    }
    
    class_counts = df['class'].value_counts().to_dict()
    browse_count = int(class_counts.get('browse', 0))
    book_count = int(class_counts.get('book', 0))
    
    status_counts = {str(k): int(v) for k, v in df['status'].value_counts().items()}
    
    hour_indices = ((df['ts'].values % 86400) // 3600).astype(int)
    hourly_counts = np.bincount(hour_indices, minlength=24)[:24]
    total_days = max(1.0, duration_s / 86400.0)
    hourly_rates = (hourly_counts / total_days / 3600.0).tolist()
    
    n_sample_points = min(300, len(rates))
    step = max(1, len(rates) // n_sample_points)
    timeline = [
        {"t_sec": round(i * bin_size, 1), "req_per_s": round(float(rates[i]), 2)}
        for i in range(0, len(rates), step)
    ]
    
    outage_info = None
    if outage_window is not None:
        outage_start, outage_end = outage_window
        outage_duration_hr = (outage_end - outage_start) / 3600.0
        post_mask = (df['ts'] >= outage_end) & (df['ts'] <= outage_end + 3600)
        surge_rate = float(post_mask.sum() / 3600.0) if post_mask.sum() > 0 else 0.0
        outage_info = {
            "start_s": round(outage_start, 1),
            "end_s": round(outage_end, 1),
            "duration_hours": round(outage_duration_hr, 2),
            "surge_recovery_req_per_s": round(surge_rate, 2),
            "description": "Hurricane Erin server shutdown and post-recovery arrival burst"
        }
        
    return {
        "trace_name": trace_name,
        "total_requests": total_reqs,
        "duration_seconds": round(duration_s, 2),
        "duration_days": round(duration_s / 86400.0, 2),
        "avg_req_per_s": round(avg_rate, 2),
        "p50_req_per_s": round(p50_rate, 2),
        "p95_req_per_s": round(p95_rate, 2),
        "p99_req_per_s": round(p99_rate, 2),
        "max_req_per_s": round(max_rate, 2),
        "burstiness": {
            "hurst_parameter": round(hurst, 3),
            "index_of_dispersion": round(idc, 2),
            "interpretation": "Self-similar bursty heavy-tailed traffic" if hurst > 0.65 else "Poisson-like"
        },
        "size_distribution_bytes": size_dist,
        "service_time_distribution": st_dist,
        "class_breakdown": {
            "browse": browse_count,
            "book": book_count,
            "book_ratio_pct": round(100.0 * book_count / max(1, total_reqs), 2)
        },
        "status_distribution": status_counts,
        "diurnal_hourly_rates": [round(r, 2) for r in hourly_rates],
        "timeline_sample": timeline,
        "outage": outage_info
    }

def parse_clf_log(raw_path: Path, output_parquet: Path, max_rows: int = None) -> Tuple[pd.DataFrame, float]:
    """Parse standard CLF log (NASA, ClarkNet) into unified Parquet."""
    print(f"[*] Parsing CLF log from {raw_path.name}...")
    hosts, timestamps, classes, path_groups, bytes_list, statuses, service_times = [], [], [], [], [], [], []
    clf_pattern = re.compile(r'^(\S+) - - \[([^\]]+)\] "(\S+) (\S+)[^"]*" (\d{3}) (\S+)')
    
    row_count = 0
    t0 = None
    open_fn = gzip.open if raw_path.suffix == '.gz' else open
    
    with open_fn(raw_path, 'rt', encoding='latin-1', errors='ignore') as f:
        for line in f:
            m = clf_pattern.match(line)
            if not m:
                continue
            host, date_str, method, path, status_str, bytes_str = m.groups()
            ts_epoch = parse_clf_date(date_str)
            if ts_epoch <= 0:
                continue
            if t0 is None:
                t0 = ts_epoch
            ts = ts_epoch - t0
            
            try:
                b = int(bytes_str) if bytes_str != '-' else 0
            except ValueError:
                b = 0
                
            try:
                status = int(status_str)
            except ValueError:
                status = 200
                
            req_class, path_group = categorize_request(path, method)
            s0 = BASE_OVERHEAD_BOOK_S if req_class == 'book' else BASE_OVERHEAD_BROWSE_S
            st = s0 + (b / EFFECTIVE_BANDWIDTH_BPS)
            host_h = hashlib.sha256(host.encode()).hexdigest()[:16]
            
            hosts.append(host_h)
            timestamps.append(ts)
            classes.append(req_class)
            path_groups.append(path_group)
            bytes_list.append(b)
            statuses.append(status)
            service_times.append(st)
            
            row_count += 1
            if max_rows and row_count >= max_rows:
                break
                
    df = pd.DataFrame({
        'ts': timestamps,
        'host_hash': hosts,
        'class': classes,
        'path_group': path_groups,
        'bytes': bytes_list,
        'status': statuses,
        'service_time_s': service_times
    }).sort_values(by='ts').reset_index(drop=True)
    
    table = pa.Table.from_pandas(df)
    pq.write_table(table, output_parquet, compression='snappy')
    print(f"[+] Successfully wrote {len(df)} rows to {output_parquet}")
    return df, t0

def parse_epa_log(raw_path: Path, output_parquet: Path, max_rows: int = None) -> pd.DataFrame:
    """Parse EPA HTTP log into unified Parquet."""
    print(f"[*] Parsing EPA log from {raw_path.name}...")
    hosts, timestamps, classes, path_groups, bytes_list, statuses, service_times = [], [], [], [], [], [], []
    epa_pattern = re.compile(r'^(\S+)\s+\[([^\]]+)\]\s+"(\S+)\s+(\S+)[^"]*"\s+(\d{3})\s+(\S+)')
    
    proc = subprocess.Popen(['7z', 'x', '-so', str(raw_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    t0 = None
    row_count = 0
    
    for line_bytes in proc.stdout:
        line = line_bytes.decode('latin-1', errors='ignore')
        m = epa_pattern.match(line)
        if not m:
            continue
        host, date_str, method, path, status_str, bytes_str = m.groups()
        ts_epoch = parse_epa_date(date_str)
        if ts_epoch <= 0:
            continue
        if t0 is None:
            t0 = ts_epoch
        ts = ts_epoch - t0
        
        b = int(bytes_str) if bytes_str.isdigit() else 0
        status = int(status_str) if status_str.isdigit() else 200
        req_class, path_group = categorize_request(path, method)
        
        s0 = BASE_OVERHEAD_BOOK_S if req_class == 'book' else BASE_OVERHEAD_BROWSE_S
        st = s0 + (b / EFFECTIVE_BANDWIDTH_BPS)
        host_h = hashlib.sha256(host.encode()).hexdigest()[:16]
        
        hosts.append(host_h)
        timestamps.append(ts)
        classes.append(req_class)
        path_groups.append(path_group)
        bytes_list.append(b)
        statuses.append(status)
        service_times.append(st)
        
        row_count += 1
        if max_rows and row_count >= max_rows:
            break
            
    proc.stdout.close()
    proc.wait()
    
    df = pd.DataFrame({
        'ts': timestamps,
        'host_hash': hosts,
        'class': classes,
        'path_group': path_groups,
        'bytes': bytes_list,
        'status': statuses,
        'service_time_s': service_times
    }).sort_values(by='ts').reset_index(drop=True)
    table = pa.Table.from_pandas(df)
    pq.write_table(table, output_parquet, compression='snappy')
    print(f"[+] Successfully wrote {len(df)} rows to {output_parquet}")
    return df

def parse_sdsc_log(raw_path: Path, output_parquet: Path, max_rows: int = None) -> pd.DataFrame:
    """Parse SDSC HTTP log into unified Parquet."""
    print(f"[*] Parsing SDSC log from {raw_path.name}...")
    hosts, timestamps, classes, path_groups, bytes_list, statuses, service_times = [], [], [], [], [], [], []
    sdsc_pattern = re.compile(r'^(\S+):\s+([A-Za-z]{3}\s+[A-Za-z]{3}\s+\d+\s+\d{2}:\d{2}:\d{2}\s+\d{4})\s+\([^)]+\):\s+Sent\s+\w+:\s+(\S+)\s+(\S+)')
    
    proc = subprocess.Popen(['7z', 'x', '-so', str(raw_path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    t0 = None
    row_count = 0
    
    for line_bytes in proc.stdout:
        line = line_bytes.decode('latin-1', errors='ignore')
        m = sdsc_pattern.match(line)
        if not m:
            continue
        client, date_str, method, path = m.groups()
        ts_epoch = parse_sdsc_date(date_str)
        if ts_epoch <= 0:
            continue
        if t0 is None:
            t0 = ts_epoch
        ts = ts_epoch - t0
        
        b = 3200  # Median web asset size
        status = 200
        req_class, path_group = categorize_request(path, method)
        s0 = BASE_OVERHEAD_BOOK_S if req_class == 'book' else BASE_OVERHEAD_BROWSE_S
        st = s0 + (b / EFFECTIVE_BANDWIDTH_BPS)
        host_h = hashlib.sha256(client.encode()).hexdigest()[:16]
        
        hosts.append(host_h)
        timestamps.append(ts)
        classes.append(req_class)
        path_groups.append(path_group)
        bytes_list.append(b)
        statuses.append(status)
        service_times.append(st)
        
        row_count += 1
        if max_rows and row_count >= max_rows:
            break
            
    proc.stdout.close()
    proc.wait()
    
    df = pd.DataFrame({
        'ts': timestamps,
        'host_hash': hosts,
        'class': classes,
        'path_group': path_groups,
        'bytes': bytes_list,
        'status': statuses,
        'service_time_s': service_times
    }).sort_values(by='ts').reset_index(drop=True)
    table = pa.Table.from_pandas(df)
    pq.write_table(table, output_parquet, compression='snappy')
    print(f"[+] Successfully wrote {len(df)} rows to {output_parquet}")
    return df

def parse_azure_log(raw_path: Path, output_parquet: Path, max_rows: int = 500000) -> pd.DataFrame:
    """Parse Azure Functions Invocation 2021 trace into unified Parquet."""
    print(f"[*] Parsing Azure Functions 2021 log from {raw_path.name} (sampling {max_rows} rows)...")
    hosts, timestamps, classes, path_groups, bytes_list, statuses, service_times = [], [], [], [], [], [], []
    
    open_fn = gzip.open if raw_path.suffix == '.gz' else open
    t0 = None
    row_count = 0
    
    with open_fn(raw_path, 'rt', encoding='utf-8', errors='ignore') as f:
        header = f.readline()  # Skip app,func,end_timestamp,duration
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(',')
            if len(parts) != 4:
                continue
            app, func, end_ts_str, dur_str = parts
            try:
                end_ts = float(end_ts_str)
                duration = float(dur_str)
            except ValueError:
                continue
                
            start_ts = end_ts - duration
            if t0 is None:
                t0 = start_ts
            ts = start_ts - t0
            if ts < 0:
                ts = 0.0
                
            st = max(0.001, duration)
            req_class = "book" if duration > 0.040 else "browse"
            path_group = f"/func/{func[:8]}"
            b = int(duration * 25000)
            
            hosts.append(app[:16])
            timestamps.append(ts)
            classes.append(req_class)
            path_groups.append(path_group)
            bytes_list.append(b)
            statuses.append(200)
            service_times.append(st)
            
            row_count += 1
            if max_rows and row_count >= max_rows:
                break
                
    df = pd.DataFrame({
        'ts': timestamps,
        'host_hash': hosts,
        'class': classes,
        'path_group': path_groups,
        'bytes': bytes_list,
        'status': statuses,
        'service_time_s': service_times
    }).sort_values(by='ts').reset_index(drop=True)
    table = pa.Table.from_pandas(df)
    pq.write_table(table, output_parquet, compression='snappy')
    print(f"[+] Successfully wrote {len(df)} rows to {output_parquet}")
    return df

def main():
    base_dir = Path(__file__).resolve().parent.parent / "data"
    raw_dir, proc_dir = ensure_dirs(base_dir)
    
    metadata = {}
    
    # 1. EPA trace (Instant demo preset)
    epa_raw = raw_dir / "epa-http.txt.Z"
    epa_proc = proc_dir / "epa.parquet"
    if epa_raw.exists():
        df_epa = parse_epa_log(epa_raw, epa_proc)
        metadata["epa"] = generate_metadata_summary("epa", df_epa)
        
    # 2. SDSC trace (Compact demo preset)
    sdsc_raw = raw_dir / "sdsc-http.txt.Z"
    sdsc_proc = proc_dir / "sdsc.parquet"
    if sdsc_raw.exists():
        df_sdsc = parse_sdsc_log(sdsc_raw, sdsc_proc)
        metadata["sdsc"] = generate_metadata_summary("sdsc", df_sdsc)
        
    # 3. Azure Functions 2021 trace (Real service duration)
    azure_raw = raw_dir / "azure.csv.gz"
    if not azure_raw.exists():
        azure_raw = raw_dir / "AzureFunctionsInvocationTraceForTwoWeeksJan2021.txt"
    azure_proc = proc_dir / "azure.parquet"
    if azure_raw.exists():
        df_azure = parse_azure_log(azure_raw, azure_proc, max_rows=300000)
        metadata["azure"] = generate_metadata_summary("azure", df_azure)
        
    # 4. NASA July 1995 trace (Primary baseline & flash crowd)
    nasa_jul_raw = raw_dir / "NASA_access_log_Jul95.gz"
    nasa_jul_proc = proc_dir / "nasa_jul95.parquet"
    if nasa_jul_raw.exists():
        df_nasa_jul, _ = parse_clf_log(nasa_jul_raw, nasa_jul_proc, max_rows=400000)
        metadata["nasa_jul95"] = generate_metadata_summary("nasa_jul95", df_nasa_jul)
        
    # 5. NASA August 1995 trace (Hurricane Erin Outage & Recovery)
    nasa_aug_raw = raw_dir / "NASA_access_log_Aug95.gz"
    nasa_aug_proc = proc_dir / "nasa_aug95.parquet"
    if nasa_aug_raw.exists():
        df_nasa_aug, t0_aug = parse_clf_log(nasa_aug_raw, nasa_aug_proc, max_rows=400000)
        # Hurricane Erin: 01 Aug 1995 14:52 to 03 Aug 1995 04:36 UTC
        dt_outage_start = datetime(1995, 8, 1, 14, 52, 1).timestamp()
        dt_outage_end = datetime(1995, 8, 3, 4, 36, 13).timestamp()
        outage_window = (dt_outage_start - t0_aug, dt_outage_end - t0_aug)
        metadata["nasa_aug95"] = generate_metadata_summary("nasa_aug95", df_nasa_aug, outage_window=outage_window)
        
    # 6. ClarkNet trace (Commercial ISP high burstiness)
    clark_raw = raw_dir / "clarknet_access_log_Aug28.gz"
    clark_proc = proc_dir / "clarknet.parquet"
    if clark_raw.exists():
        df_clark, _ = parse_clf_log(clark_raw, clark_proc, max_rows=400000)
        metadata["clarknet"] = generate_metadata_summary("clarknet", df_clark)
        
    # Write precomputed metadata
    meta_path = proc_dir / "traces_metadata.json"
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"[✓] Complete Dataset Explorer metadata generated and saved to {meta_path}")

if __name__ == "__main__":
    main()
