#!/bin/bash

# Simple development script to start both backend and frontend
# This is an alternative to using make or npm

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${BLUE}Starting Jaeger Development Environment${NC}"
echo ""

# Check if uvicorn is available
if [ ! -f .venv/bin/uvicorn ]; then
    echo -e "${YELLOW}Warning: uvicorn not found in .venv${NC}"
    echo "Please run: make install"
    exit 1
fi

# Check if node_modules exists
if [ ! -d jaeger-ui/node_modules ]; then
    echo -e "${YELLOW}Warning: Node modules not installed${NC}"
    echo "Please run: cd jaeger-ui && npm install"
    exit 1
fi

# Function to cleanup background processes on exit
cleanup() {
    echo ""
    echo -e "${YELLOW}Shutting down servers...${NC}"
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo -e "${GREEN}Servers stopped${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start backend
echo -e "${GREEN}Starting backend on http://localhost:8000${NC}"
.venv/bin/uvicorn app:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Give backend a moment to start
sleep 2

# Start frontend
echo -e "${GREEN}Starting frontend on http://localhost:5173${NC}"
cd jaeger-ui && npm start &
FRONTEND_PID=$!

echo ""
echo -e "${BLUE}Jaeger is running!${NC}"
echo -e "  Backend:  ${GREEN}http://localhost:8000${NC}"
echo -e "  Frontend: ${GREEN}http://localhost:5173${NC}"
echo ""
echo "Press Ctrl+C to stop both servers"
echo ""

# Wait for both processes
wait $BACKEND_PID $FRONTEND_PID
