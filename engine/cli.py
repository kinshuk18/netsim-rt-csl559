"""
NetSim-RT Command-Line Interface
CSL559 Computer Systems Design - IIT Bhilai
"""

import sys
import json
import argparse
from pathlib import Path
from engine.models import SimulationConfig
from engine.simulator import Simulator
from engine.policies.base import list_available_policies


def run_single(args) -> dict:
    config = SimulationConfig(
        trace_path=args.trace,
        policy=args.policy,
        num_servers=args.servers,
        load_multiplier=args.load,
        time_quantum=args.quantum / 1000.0,
        slo_target_s=args.slo / 1000.0,
        queue_capacity=args.capacity,
        client_timeout=args.timeout,
        max_requests=args.max_requests,
        window_start_s=args.window_start,
        window_duration_s=args.window_duration
    )
    sim = Simulator(config)
    result = sim.run()
    return result.to_dict()


def run_shootout(args) -> dict:
    policies = list_available_policies()
    shootout_results = {}
    print(f"[*] Running Policy Shootout across {len(policies)} policies on {args.trace}...")
    
    for pol in policies:
        print(f"  -> Testing {pol.upper()}...", end="", flush=True)
        config = SimulationConfig(
            trace_path=args.trace,
            policy=pol,
            num_servers=args.servers,
            load_multiplier=args.load,
            time_quantum=args.quantum / 1000.0,
            slo_target_s=args.slo / 1000.0,
            queue_capacity=args.capacity,
            client_timeout=args.timeout,
            max_requests=args.max_requests,
            window_start_s=args.window_start,
            window_duration_s=args.window_duration
        )
        sim = Simulator(config)
        res = sim.run()
        shootout_results[pol] = res.to_dict()
        print(f" p99: {res.latency_p99*1000.0:.1f}ms, goodput: {res.goodput_req_per_s:.1f} r/s, speed: {res.events_per_sec:.0f} ev/s")
        
    return shootout_results


def main():
    parser = argparse.ArgumentParser(description="NetSim-RT Discrete-Event Simulator CLI")
    parser.add_argument("--trace", type=str, default="data/processed/epa.parquet", help="Path to Parquet trace file")
    parser.add_argument("--policy", type=str, default="fcfs", choices=list_available_policies(), help="Scheduling policy")
    parser.add_argument("--servers", type=int, default=4, help="Number of worker servers (default: 4)")
    parser.add_argument("--load", type=float, default=1.0, help="Load multiplier factor (default: 1.0)")
    parser.add_argument("--quantum", type=float, default=10.0, help="Round Robin / MLFQ quantum in milliseconds (default: 10ms)")
    parser.add_argument("--slo", type=float, default=500.0, help="SLO latency target in milliseconds (default: 500ms)")
    parser.add_argument("--capacity", type=int, default=50000, help="Drop-tail queue capacity (default: 50000)")
    parser.add_argument("--timeout", type=float, default=30.0, help="Client timeout in seconds (default: 30s)")
    parser.add_argument("--max-requests", type=int, default=None, help="Maximum requests to simulate")
    parser.add_argument("--window-start", type=float, default=None, help="Trace window start time in seconds")
    parser.add_argument("--window-duration", type=float, default=None, help="Trace window duration in seconds")
    parser.add_argument("--shootout", action="store_true", help="Run policy shootout comparing all registered policies")
    parser.add_argument("--output", type=str, default=None, help="Path to write JSON output")

    args = parser.parse_args()

    if args.shootout:
        res = run_shootout(args)
    else:
        res = run_single(args)

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w") as f:
            json.dump(res, f, indent=2)
        print(f"[✓] Results written to {args.output}")
    else:
        print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
