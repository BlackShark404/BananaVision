#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
#  BananaVision — Dev Startup Script
#  Starts both backend (FastAPI) and frontend (Vite) servers.
#  Usage: ./dev.sh
# ─────────────────────────────────────────────────────────

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  🍌 BananaVision — Development Environment${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# ── Check Python venv ────────────────────────────────────────────────────────
if [ ! -d "$BACKEND_DIR/venv" ]; then
  echo -e "${YELLOW}⚙  Creating Python virtual environment...${NC}"
  python3 -m venv "$BACKEND_DIR/venv"
  source "$BACKEND_DIR/venv/bin/activate"
  pip install -r "$BACKEND_DIR/requirements.txt"
else
  source "$BACKEND_DIR/venv/bin/activate"
fi

# ── Check frontend node_modules ──────────────────────────────────────────────
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo -e "${YELLOW}⚙  Installing frontend dependencies...${NC}"
  (cd "$FRONTEND_DIR" && npm install --legacy-peer-deps)
fi

# ── Kill any leftover processes on ports 8000 & 5173 ─────────────────────────
lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null || true

# ── Start backend ────────────────────────────────────────────────────────────
echo -e "${GREEN}▶  Starting Backend (FastAPI) on http://localhost:8000${NC}"
(cd "$BACKEND_DIR" && source venv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) &
BACKEND_PID=$!

# Give backend a moment to boot
sleep 3

# ── Start frontend ───────────────────────────────────────────────────────────
echo -e "${GREEN}▶  Starting Frontend (Vite) on http://localhost:5173${NC}"
(cd "$FRONTEND_DIR" && npm run dev) &
FRONTEND_PID=$!

# ── Start Sensor Debug Terminal ──────────────────────────────────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
  echo -e "${GREEN}▶  Opening Sensor Debugger in a new Terminal window${NC}"
  osascript -e 'tell app "Terminal" to do script "cd \"'$BACKEND_DIR'\" && source venv/bin/activate && python debug_sensor.py"'
else
  echo -e "${GREEN}▶  Starting Sensor Debugger in background${NC}"
  (cd "$BACKEND_DIR" && source venv/bin/activate && python debug_sensor.py) &
  DEBUGGER_PID=$!
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${GREEN}Frontend${NC}  →  http://localhost:5173"
echo -e "  ${GREEN}Backend${NC}   →  http://localhost:8000"
echo -e "  ${GREEN}API Docs${NC}  →  http://localhost:8000/docs"
echo -e "  ${GREEN}Login${NC}     →  admin / admin"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "  ${YELLOW}Press Ctrl+C to stop both servers${NC}"
echo ""

# ── Trap Ctrl+C to kill both processes ───────────────────────────────────────
cleanup() {
  echo ""
  echo -e "${YELLOW}Shutting down...${NC}"
  kill $BACKEND_PID 2>/dev/null
  kill $FRONTEND_PID 2>/dev/null
  if [ ! -z "$DEBUGGER_PID" ]; then
    kill $DEBUGGER_PID 2>/dev/null
  fi
  wait $BACKEND_PID 2>/dev/null
  wait $FRONTEND_PID 2>/dev/null
  echo -e "${GREEN}Done.${NC}"
  exit 0
}

trap cleanup SIGINT SIGTERM

# Wait for both processes
wait
