#!/usr/bin/env bash
set -e

SYS1_USER="student"
SYS1_HOST="10.1.75.40"
SYS1_PORT="2507"
APP_PORT="3507"
REMOTE_DIR="/home/student/netsim-rt"

echo "=== Deploying NetSim-RT to sys1 ($SYS1_HOST:$SYS1_PORT) ==="

# 1. Sync repository files via SSH tar pipe (reliable, no remote rsync dependency)
tar -czf - \
  --exclude ".git" \
  --exclude ".venv" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  --exclude "data/raw" \
  --exclude "report/*.aux" \
  --exclude "report/*.log" \
  --exclude "report/*.pdf" \
  . | ssh -p $SYS1_PORT "$SYS1_USER@$SYS1_HOST" "mkdir -p $REMOTE_DIR && tar -xzf - -C $REMOTE_DIR"

# 2. Remote setup and execution
ssh -p $SYS1_PORT "$SYS1_USER@$SYS1_HOST" bash << 'EOF'
set -e
cd /home/student/netsim-rt

if [ ! -d ".venv" ]; then
  echo "Creating remote virtualenv..."
  python3 -m venv .venv
fi

echo "Installing/verifying python dependencies..."
.venv/bin/pip install -q -r requirements.txt

echo "Restarting uvicorn server on port 3507..."
fuser -k 3507/tcp 2>/dev/null || true
pkill -f "uvicorn server.main:app" 2>/dev/null || true
sleep 1

setsid nohup .venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 3507 > server.log 2>&1 &

# Health check
sleep 2
for i in {1..5}; do
  if curl -s http://127.0.0.1:3507/api/health > /dev/null; then
    echo "Remote server health check PASSED on port 3507."
    exit 0
  fi
  sleep 1
done

echo "Server failed to respond on port 3507. Showing server.log:"
tail -n 20 server.log
exit 1
EOF

echo "=== Verifying from local machine ==="
curl -s "http://$SYS1_HOST:$APP_PORT/api/health"
echo ""
echo "Deployment SUCCESS! NetSim-RT is live at http://$SYS1_HOST:$APP_PORT"
