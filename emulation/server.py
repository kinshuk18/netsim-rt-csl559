"""
NetSim-RT Emulation Server (Real Running System).

Structural Correspondence with NetSim-RT Discrete-Event Simulator:
------------------------------------------------------------------
1. Architecture Mapping:
   - Simulator: Central queue (FIFO buffer) with `c` parallel server entities.
   - Emulation: A single `multiprocessing.Queue` (Central FIFO Queue) served by
     `c` independent OS worker processes.
2. Scheduling Policy:
   - Simulator: FCFS (First-Come First-Served) non-preemptive queue discipline.
   - Emulation: The OS `multiprocessing.Queue` delivers tasks strictly in arrival
     FIFO order to the first idle worker process that unblocks on `.get()`.
3. Service Time Realization:
   - Simulator: Virtual clock advance `clock += service_time_s`.
   - Emulation: Real CPU-bound busy-spin on `time.perf_counter()` for exact duration
     `service_time_s`, burning hardware CPU cycles on pinned physical cores.
4. Admission & Backpressure:
   - Simulator: Tail-drop when queue depth reaches `queue_capacity`.
   - Emulation: HTTP 503 Service Unavailable when `multiprocessing.Queue` is full.
5. Client Timeout:
   - Simulator: Event-queue timer triggers `_handle_timeout` after `client_timeout`.
   - Emulation: `asyncio.wait_for` triggers HTTP 504 Gateway Timeout if elapsed
     time exceeds `client_timeout`.
"""

import os
import sys
import time
import uuid
import queue
import logging
import argparse
import threading
import asyncio
import multiprocessing
from typing import Dict, Optional, Tuple
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
import uvicorn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("emulation_server")

# Global state containers
job_queue: Optional[multiprocessing.Queue] = None
result_queue: Optional[multiprocessing.Queue] = None
worker_processes = []
pending_futures: Dict[str, asyncio.Future] = {}
dispatcher_thread: Optional[threading.Thread] = None
dispatcher_running = False
main_loop: Optional[asyncio.AbstractEventLoop] = None


def worker_process_fn(
    worker_id: int,
    core_id: Optional[int],
    in_queue: multiprocessing.Queue,
    out_queue: multiprocessing.Queue,
):
    """Worker process: busy-spins for service_time_s on designated CPU core."""
    if core_id is not None:
        try:
            os.sched_setaffinity(0, {core_id})
            logger.info("Worker %d pinned to CPU core %d", worker_id, core_id)
        except Exception as e:
            logger.warning("Worker %d affinity error: %s", worker_id, e)

    while True:
        try:
            item = in_queue.get()
        except (KeyboardInterrupt, EOFError):
            break

        if item is None:  # Sentinel to terminate
            break

        req_id, service_time_s, t_arrive = item
        t_start = time.perf_counter()
        wait_s = t_start - t_arrive

        # CPU busy-spin: real hardware cycle execution
        target_burn = max(0.0, float(service_time_s))
        while (time.perf_counter() - t_start) < target_burn:
            pass

        t_finish = time.perf_counter()
        burn_s = t_finish - t_start

        try:
            out_queue.put((req_id, wait_s, burn_s))
        except (KeyboardInterrupt, EOFError):
            break


def result_dispatcher_loop():
    """Background thread in FastAPI process: resolves asyncio Futures from result_queue."""
    global dispatcher_running
    while dispatcher_running:
        try:
            item = result_queue.get(timeout=0.05)
        except queue.Empty:
            continue
        except (KeyboardInterrupt, EOFError):
            break

        if item is None:
            break

        req_id, wait_s, burn_s = item
        fut = pending_futures.pop(req_id, None)
        if fut and not fut.done() and main_loop and not main_loop.is_closed():
            main_loop.call_soon_threadsafe(fut.set_result, (wait_s, burn_s))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop, dispatcher_running, dispatcher_thread
    main_loop = asyncio.get_running_loop()
    dispatcher_running = True
    dispatcher_thread = threading.Thread(target=result_dispatcher_loop, daemon=True)
    dispatcher_thread.start()
    logger.info("Result dispatcher thread started.")
    yield
    dispatcher_running = False
    if dispatcher_thread:
        dispatcher_thread.join(timeout=1.0)
    for p in worker_processes:
        if p.is_alive():
            job_queue.put(None)
    for p in worker_processes:
        p.join(timeout=1.0)
        if p.is_alive():
            p.terminate()
    logger.info("Emulation server shutdown complete.")


app = FastAPI(title="NetSim-RT Real Emulation Server", lifespan=lifespan)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "num_workers": len(worker_processes),
        "pending_requests": len(pending_futures),
        "job_queue_depth": job_queue.qsize() if job_queue else 0,
    }


@app.get("/work")
async def work(
    service_time_s: float = Query(..., ge=0.0, le=10.0),
    client_timeout_s: float = Query(5.0, ge=0.01, le=60.0),
    req_id: Optional[str] = Query(None),
):
    """
    Central queue work endpoint:
    1. Enqueues job to central FIFO queue.
    2. Idle worker dequeues and busy-spins.
    3. Returns real timing metrics upon completion.
    """
    rid = req_id or uuid.uuid4().hex
    t_arrive = time.perf_counter()

    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    pending_futures[rid] = fut

    try:
        job_queue.put_nowait((rid, service_time_s, t_arrive))
    except queue.Full:
        pending_futures.pop(rid, None)
        raise HTTPException(status_code=503, detail="Central queue capacity exhausted (drop-tail)")

    try:
        wait_s, burn_s = await asyncio.wait_for(fut, timeout=client_timeout_s)
    except asyncio.TimeoutError:
        pending_futures.pop(rid, None)
        raise HTTPException(status_code=504, detail="Client timeout exceeded")

    t_total = time.perf_counter() - t_arrive
    return {
        "status": "completed",
        "req_id": rid,
        "wait_s": wait_s,
        "burn_s": burn_s,
        "latency_s": t_total,
    }


def start_server(
    host: str = "127.0.0.1",
    port: int = 8008,
    num_workers: int = 4,
    queue_capacity: int = 20000,
    worker_cores: Optional[str] = "0,1,2,3",
):
    global job_queue, result_queue, worker_processes

    # Use multiprocessing fork or spawn
    ctx = multiprocessing.get_context("spawn")
    job_queue = ctx.Queue(maxsize=queue_capacity)
    result_queue = ctx.Queue(maxsize=queue_capacity)

    assigned_cores = [int(c.strip()) for c in worker_cores.split(",")] if worker_cores else [None] * num_workers
    while len(assigned_cores) < num_workers:
        assigned_cores.append(None)

    worker_processes = []
    for w_id in range(num_workers):
        core = assigned_cores[w_id]
        p = ctx.Process(
            target=worker_process_fn,
            args=(w_id, core, job_queue, result_queue),
            daemon=True,
        )
        p.start()
        worker_processes.append(p)

    logger.info("Spawned %d worker processes (cores=%s)", num_workers, assigned_cores[:num_workers])
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NetSim-RT Real Emulation Server")
    parser.add_argument("--host", type=str, default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8008)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--queue-capacity", type=int, default=20000)
    parser.add_argument("--worker-cores", type=str, default="0,1,2,3")
    args = parser.parse_args()

    start_server(
        host=args.host,
        port=args.port,
        num_workers=args.workers,
        queue_capacity=args.queue_capacity,
        worker_cores=args.worker_cores,
    )
