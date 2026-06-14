#!/bin/bash

# ─────────────────────────────────────────────────────────
#  BananaVision — Edge Node Startup Script (Linux Production)
#  Starts backend and serves frontend statically.
# ─────────────────────────────────────────────────────────

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo "============================================================"
echo "  BananaVision - Edge Node Startup (Linux Production Mode)"
echo "============================================================"

# 1. Backend Setup
if [ ! -d "$BACKEND_DIR/venv" ]; then
    echo "[INFO] Creating Python virtual environment..."
    python3 -m venv "$BACKEND_DIR/venv"
    source "$BACKEND_DIR/venv/bin/activate"
    pip install -r "$BACKEND_DIR/requirements.txt"
else
    source "$BACKEND_DIR/venv/bin/activate"
fi

# 2. Frontend Setup
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "[INFO] Installing frontend dependencies..."
    cd "$FRONTEND_DIR" || exit
    npm install
    cd "$ROOT_DIR" || exit
fi

if [ ! -d "$FRONTEND_DIR/dist" ]; then
    echo "[INFO] Building Frontend for Production..."
    cd "$FRONTEND_DIR" || exit
    npm run build
    cd "$ROOT_DIR" || exit
fi

# 3. Clean up ports
echo "[INFO] Cleaning up ports 8000 and 5173..."
fuser -k 8000/tcp 2>/dev/null
fuser -k 5173/tcp 2>/dev/null

# 4. Start Backend
echo "[INFO] Starting Backend (FastAPI Production Mode)..."
cd "$BACKEND_DIR" || exit
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Give backend a moment to boot
sleep 3

# 5. Start Frontend
echo "[INFO] Starting Frontend (Static Serve)..."
cd "$FRONTEND_DIR" || exit
npm run preview -- --host 0.0.0.0 --port 5173 &
FRONTEND_PID=$!

# 6. Launch Kiosk Mode UI
echo "[INFO] Waiting for UI to become available..."
sleep 3
echo "[INFO] Launching Kiosk Interface..."

if command -v chromium-browser &> /dev/null; then
    chromium-browser --kiosk "http://localhost:5173/kiosk" &
elif command -v google-chrome &> /dev/null; then
    google-chrome --kiosk "http://localhost:5173/kiosk" &
else
    echo "[WARNING] Could not find chromium or google-chrome to launch Kiosk."
fi

echo ""
echo "============================================================"
echo "  System is now LIVE on your local network."
echo "  Frontend (Kiosk/Dashboard) -> http://localhost:5173"
echo "  Backend API                -> http://localhost:8000"
echo "============================================================"
echo "Press [CTRL+C] to stop servers."
echo ""

# Wait to keep the script running
wait $BACKEND_PID $FRONTEND_PID
