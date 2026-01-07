#!/bin/bash

# x402 Demo Startup Script
# Starts API server and frontend for filming

set -e

echo "=========================================="
echo "  x402 + Stablecoins Demo"
echo "=========================================="
echo ""

# Check .env exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    echo "Copy .env.example to .env and fill in your keys"
    exit 1
fi

# Load .env
source .env

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Check required vars
if [ -z "$AGENT_PRIVATE_KEY" ] || [ "$AGENT_PRIVATE_KEY" = "your_64_character_private_key_here" ]; then
    echo "ERROR: AGENT_PRIVATE_KEY not set in .env"
    exit 1
fi

if [ -z "$RECIPIENT_ADDRESS" ] || [ "$RECIPIENT_ADDRESS" = "0x_incumbent_metamask_address_here" ]; then
    echo "ERROR: RECIPIENT_ADDRESS not set in .env"
    exit 1
fi

echo "Starting services..."
echo ""

# Kill any existing processes on our ports
echo "Cleaning up old processes..."
lsof -ti:8888 | xargs kill -9 2>/dev/null || true
lsof -ti:3000 | xargs kill -9 2>/dev/null || true
sleep 1

# Start API server
echo "Starting API server on http://localhost:8888"
cd api
python3 -m uvicorn main:app --host 127.0.0.1 --port 8888 --reload > /tmp/x402_api.log 2>&1 &
API_PID=$!
cd ..

# Wait for API to be ready
echo "Waiting for API..."
for i in {1..30}; do
    if curl -s http://localhost:8888/health > /dev/null 2>&1; then
        echo "API ready!"
        break
    fi
    sleep 1
done

# Start frontend server
echo "Starting frontend on http://localhost:3000"
cd frontend
python3 -m http.server 3000 > /tmp/x402_frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

sleep 2

echo ""
echo "=========================================="
echo "  READY FOR FILMING!"
echo "=========================================="
echo ""
echo "  Frontend: http://localhost:3000"
echo "  API:      http://localhost:8888"
echo "  API Docs: http://localhost:8888/docs"
echo ""
echo "  Press Ctrl+C to stop all services"
echo "=========================================="
echo ""

# Open browser
if command -v open &> /dev/null; then
    open http://localhost:3000
fi

# Wait for Ctrl+C
trap "echo ''; echo 'Stopping services...'; kill $API_PID $FRONTEND_PID 2>/dev/null; exit 0" INT
wait
