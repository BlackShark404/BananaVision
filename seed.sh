#!/bin/bash

# ─────────────────────────────────────────────────────────
#  BananaVision — Database Seeder Script (Linux/macOS)
# ─────────────────────────────────────────────────────────

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"

echo "============================================================"
echo "  BananaVision - Running Database Seeder"
echo "============================================================"

set -e

# Activate virtual environment
if [ -d "$BACKEND_DIR/venv" ]; then
    source "$BACKEND_DIR/venv/bin/activate"
else
    echo "[ERROR] Virtual environment not found. Please run setup.sh first."
    exit 1
fi

# Run the seeder
echo "[WARNING] Demo seeding deletes existing application database records, including accounts, scans and history."
echo "Use a development database only. Choose N to keep your existing database."
read -r -p "Reset the application database and seed demo data now? (y/N): " reset_demo
if [[ ! "$reset_demo" =~ ^[Yy]$ ]]; then
    echo "[INFO] Skipping database seeding."
    exit 0
fi
cd "$BACKEND_DIR" || exit
python seed.py --reset-demo

echo ""
echo "[INFO] Seeding completed successfully."
echo "============================================================"
