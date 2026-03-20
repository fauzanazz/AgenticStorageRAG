#!/usr/bin/env bash
# dev.sh - Run the full dev stack without Docker for app services.
# Infrastructure (Neo4j + Redis) runs in Docker; backend, worker, and frontend run natively in tmux.
#
# Usage:
#   ./dev.sh          Start all services
#   ./dev.sh stop     Stop tmux session and Docker infra

set -euo pipefail

SESSION="openrag"
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Stop mode ──────────────────────────────────────────────────
if [[ "${1:-}" == "stop" ]]; then
  echo "Stopping tmux session '$SESSION'..."
  tmux kill-session -t "$SESSION" 2>/dev/null || true
  echo "Stopping Docker infrastructure..."
  docker compose -f "$ROOT_DIR/docker-compose.yml" stop neo4j redis
  exit 0
fi

# ── Pre-flight checks ─────────────────────────────────────────
for cmd in tmux docker uv pnpm; do
  if ! command -v "$cmd" &>/dev/null; then
    echo "Error: '$cmd' is not installed." >&2
    exit 1
  fi
done

if [[ ! -f "$ROOT_DIR/.env" ]]; then
  echo "Error: .env file not found. Copy .env.example to .env first." >&2
  exit 1
fi

# ── Start Docker infrastructure (Neo4j + Redis only) ──────────
echo "Starting Neo4j and Redis via Docker..."
docker compose -f "$ROOT_DIR/docker-compose.yml" up -d neo4j redis

# Wait for services to be healthy
echo "Waiting for Neo4j and Redis to be ready..."
for svc in neo4j redis; do
  timeout=60
  while [[ $timeout -gt 0 ]]; do
    status=$(docker compose -f "$ROOT_DIR/docker-compose.yml" ps "$svc" --format json 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('Health',''))" 2>/dev/null || echo "")
    if [[ "$status" == "healthy" ]]; then
      echo "  $svc is healthy"
      break
    fi
    sleep 2
    timeout=$((timeout - 2))
  done
  if [[ $timeout -le 0 ]]; then
    echo "Warning: $svc did not become healthy within 60s, continuing anyway..."
  fi
done

# ── Kill existing tmux session if any ──────────────────────────
tmux kill-session -t "$SESSION" 2>/dev/null || true

# ── Source .env for local processes ────────────────────────────
ENV_EXPORT="set -a && source $ROOT_DIR/.env && set +a"

# Override Neo4j/Redis to use Docker-exposed ports on localhost
NEO4J_OVERRIDE="export NEO4J_URI=bolt://localhost:17687 NEO4J_USER=neo4j NEO4J_PASSWORD=dingdong_dev NEO4J_DATABASE=dingdongrag"
REDIS_OVERRIDE="export REDIS_URL=redis://localhost:16379/0"

# ── Create tmux session with 3 panes ──────────────────────────
echo "Starting tmux session '$SESSION'..."

# Window 1: Backend
tmux new-session -d -s "$SESSION" -n "backend" -c "$ROOT_DIR/backend"
tmux send-keys -t "$SESSION:backend" "$ENV_EXPORT && $NEO4J_OVERRIDE && $REDIS_OVERRIDE && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload" Enter

# Window 2: Worker
tmux new-window -t "$SESSION" -n "worker" -c "$ROOT_DIR/backend"
tmux send-keys -t "$SESSION:worker" "$ENV_EXPORT && $NEO4J_OVERRIDE && $REDIS_OVERRIDE && uv run celery -A app.celery_app worker --loglevel=info --queues=documents,ingestion --concurrency=4 --pool=threads" Enter

# Window 3: Frontend
tmux new-window -t "$SESSION" -n "frontend" -c "$ROOT_DIR/frontend"
tmux send-keys -t "$SESSION:frontend" "NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1 pnpm dev" Enter

echo ""
echo "All services started in tmux session '$SESSION'"
echo ""
echo "  tmux attach -t $SESSION     Attach to session"
echo "  ./dev.sh stop               Stop everything"
echo ""
echo "Windows:"
echo "  0:backend   → uvicorn on :8000"
echo "  1:worker    → celery worker"
echo "  2:frontend  → next dev on :3000"
