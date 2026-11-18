#!/usr/bin/env bash
ssh -p 2507 student@10.1.75.40 "cd /home/student/netsim-rt && fuser -k 3507/tcp 2>/dev/null || true; pkill -f 'uvicorn server.main:app' 2>/dev/null || true; sleep 1; setsid nohup .venv/bin/uvicorn server.main:app --host 0.0.0.0 --port 3507 > server.log 2>&1 & sleep 2; curl -s http://127.0.0.1:3507/api/health"
