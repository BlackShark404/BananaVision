#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────
#  BananaVision — Project Setup Script
#  Run this script once to initialize the project environment.
# ─────────────────────────────────────────────────────────

set -e

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

# Colors
GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  🍌 BananaVision — Project Setup${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# 1. Backend .env
echo -e "${YELLOW}⚙  Setting up backend environment variables...${NC}"
if [ ! -f "$BACKEND_DIR/.env" ]; then
    cp "$BACKEND_DIR/.env.example" "$BACKEND_DIR/.env"
    echo -e "${GREEN}✔ Created backend/.env from .env.example${NC}"
else
    echo -e "${YELLOW}ℹ backend/.env already exists, skipping.${NC}"
fi

# 2. Frontend .env
echo -e "${YELLOW}⚙  Setting up frontend environment variables...${NC}"
if [ ! -f "$FRONTEND_DIR/.env" ]; then
    if [ -f "$FRONTEND_DIR/.env.development" ]; then
        cp "$FRONTEND_DIR/.env.development" "$FRONTEND_DIR/.env"
        echo -e "${GREEN}✔ Created frontend/.env from .env.development${NC}"
    else
        echo -e "${YELLOW}ℹ No .env.development found in frontend, skipping.${NC}"
    fi
else
    echo -e "${YELLOW}ℹ frontend/.env already exists, skipping.${NC}"
fi

# 3. Backend Dependencies
echo -e "${YELLOW}⚙  Setting up Python virtual environment and dependencies...${NC}"
if [ ! -d "$BACKEND_DIR/venv" ]; then
    python3 -m venv "$BACKEND_DIR/venv"
fi
source "$BACKEND_DIR/venv/bin/activate"
python3 -m pip install --upgrade pip
pip install -r "$BACKEND_DIR/requirements.txt"
echo -e "${GREEN}✔ Backend dependencies installed.${NC}"

# 4. Frontend Dependencies
echo -e "${YELLOW}⚙  Setting up Frontend dependencies...${NC}"
(cd "$FRONTEND_DIR" && npm install --legacy-peer-deps)
echo -e "${GREEN}✔ Frontend dependencies installed.${NC}"

# 5. Database Seeding
echo -e "${YELLOW}⚙  Checking Database and Seeding...${NC}"
echo -e "${CYAN}Note: Make sure your PostgreSQL server is running and the database 'bananavision' is created as per your backend/.env configuration.${NC}"
read -p "Do you want to seed the database now? (y/n): " seed_db
if [[ "$seed_db" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}⚙  Seeding database...${NC}"
    (cd "$BACKEND_DIR" && source venv/bin/activate && python3 seed.py)
    echo -e "${GREEN}✔ Database seeded.${NC}"
else
    echo -e "${YELLOW}ℹ Skipping database seeding.${NC}"
fi

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Setup Complete! 🍌${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "You can now run the application using:"
echo -e "  ${GREEN}./dev.sh${NC} (macOS/Linux) or ${GREEN}dev.bat${NC} (Windows)"
echo ""
