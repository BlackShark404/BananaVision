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
    
    # Auto-generate secure secret keys
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    JWT_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    
    # Replace placeholders in the new .env (works on macOS/BSD and GNU sed)
    sed -i.bak "s/APP_SECRET_KEY=.*/APP_SECRET_KEY=$SECRET_KEY/" "$BACKEND_DIR/.env"
    sed -i.bak "s/JWT_SECRET_KEY=.*/JWT_SECRET_KEY=$JWT_KEY/" "$BACKEND_DIR/.env"
    rm -f "$BACKEND_DIR/.env.bak"
    
    echo -e "${GREEN}✔ Created backend/.env and generated secure secret keys${NC}"
    
    # Prompt for database credentials
    echo ""
    echo -e "${YELLOW}⚙  Database Configuration${NC}"
    read -p "Do you want to configure database credentials now? (y/n): " config_db
    if [[ "$config_db" =~ ^[Yy]$ ]]; then
        read -p "PostgreSQL Username [postgres]: " DB_USER
        DB_USER=${DB_USER:-postgres}
        
        read -s -p "PostgreSQL Password: " DB_PASS
        echo ""
        
        read -p "PostgreSQL Host [localhost]: " DB_HOST
        DB_HOST=${DB_HOST:-localhost}
        
        read -p "PostgreSQL Port [5432]: " DB_PORT
        DB_PORT=${DB_PORT:-5432}
        
        read -p "Database Name [bananavision]: " DB_NAME
        DB_NAME=${DB_NAME:-bananavision}
        
        export NEW_DB_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
        python3 -c "import os, re; p='$BACKEND_DIR/.env'; c=open(p).read(); c=re.sub(r'^DATABASE_URL=.*', 'DATABASE_URL=' + os.environ['NEW_DB_URL'], c, flags=re.MULTILINE); open(p,'w').write(c)"
        echo -e "${GREEN}✔ Database configuration saved to .env${NC}"
    else
        echo -e "${YELLOW}ℹ Skipping database configuration. (Using defaults)${NC}"
    fi
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
echo "[WARNING] Demo seeding deletes existing application database records, including accounts, scans and history."
echo "It recreates demo data with VPD and current Scan Logs fields. Use a development database only."
echo "Seeding requires BOOTSTRAP_ADMIN_PASSWORD. Choose N to keep your existing database."
read -r -p "Reset the application database and seed demo data now? (y/N): " seed_db
if [[ "$seed_db" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}⚙  Seeding database...${NC}"
    if (cd "$BACKEND_DIR" && source venv/bin/activate && python3 seed.py --reset-demo); then
        echo -e "${GREEN}✔ Database seeded.${NC}"
    else
        seed_exit=$?
        echo "[ERROR] Database seeding failed. Check backend/.env and the error above."
        exit "$seed_exit"
    fi
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
