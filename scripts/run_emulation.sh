#!/usr/bin/env bash
set -e

PORT=8008
WORKERS=4
WORKER_CORES="0,1,2,3"
LOADGEN_CORES="8,9,10,11,12,13,14,15"
PYTHON=".venv/bin/python"

echo "=== [1/4] Starting NetSim-RT Real Emulation Server on port $PORT ==="
fuser -k $PORT/tcp 2>/dev/null || true
pkill -f "emulation/server.py" 2>/dev/null || true
sleep 1

# Start server in background
$PYTHON emulation/server.py --port $PORT --workers $WORKERS --worker-cores "$WORKER_CORES" > emulation_server.log 2>&1 &
SERVER_PID=$!

echo "Waiting for server to become healthy (PID=$SERVER_PID)..."
for i in {1..30}; do
  if curl -s http://127.0.0.1:$PORT/health | grep -q '"status":"ok"'; then
    echo "Emulation server is ready on port $PORT."
    break
  fi
  sleep 0.5
done

# Double-check health
if ! curl -s http://127.0.0.1:$PORT/health | grep -q '"status":"ok"'; then
  echo "Server failed to start. Logs:"
  cat emulation_server.log | tail -n 20
  kill $SERVER_PID 2>/dev/null || true
  exit 1
fi

echo "=== [2/4] Running Real Trace Load Generator (6 rho levels, 20s each) ==="
$PYTHON emulation/loadgen.py \
  --trace data/processed/nasa_jul95.parquet \
  --url http://127.0.0.1:$PORT \
  --servers $WORKERS \
  --dilation 2.5 \
  --duration 20.0 \
  --cores "$LOADGEN_CORES" \
  --output results/emulation_results.json

echo "=== [3/4] Stopping Emulation Server ==="
kill $SERVER_PID 2>/dev/null || true
fuser -k $PORT/tcp 2>/dev/null || true
sleep 1

echo "=== [4/4] Comparing Emulation vs Discrete-Event Simulator ==="
PYTHONPATH=. $PYTHON emulation/compare.py \
  --emulation-results results/emulation_results.json \
  --trace data/processed/nasa_jul95.parquet \
  --output results/validation.json

echo "Validation complete! Output saved to results/validation.json"
