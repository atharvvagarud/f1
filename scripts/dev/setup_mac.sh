#!/bin/bash
set -e

echo "Setting up F1 Race Winner Predictor project on macOS..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$ROOT"

echo ""
echo "[1/4] Creating Python virtual environment..."

if [ ! -d "venv" ]; then
  python3 -m venv venv
else
  echo "venv already exists, skipping creation."
fi

echo ""
echo "[2/4] Activating virtual environment..."
source venv/bin/activate

echo ""
echo "[3/4] Installing Python dependencies..."
python -m pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "[4/4] Installing frontend dependencies..."
cd frontend
npm install

echo ""
echo "Setup complete."
echo ""
echo "Backend:"
echo "python -m uvicorn api.main:app --reload --reload-dir api"
echo ""
echo "Frontend:"
echo "cd frontend && npm run dev"