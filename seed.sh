#!/bin/bash

# ─────────────────────────────────────────────────────────
#  BananaVision — Database Seeder Script (Linux/macOS)
# ─────────────────────────────────────────────────────────

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

echo "============================================================"
echo "  BananaVision - Running Database Seeder"
echo "============================================================"

# Activate virtual environment
if [ -d "$BACKEND_DIR/venv" ]; then
    source "$BACKEND_DIR/venv/bin/activate"
else
    echo "[ERROR] Virtual environment not found. Please run setup.sh first."
    exit 1
fi

# Run the seeder
cd "$BACKEND_DIR" || exit
python seed.py

echo ""
echo "[INFO] Seeding completed successfully."
echo "============================================================"
