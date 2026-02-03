.PHONY: help install dev dev-backend dev-frontend build build-ui clean

# Default target
help:
	@echo "Jaeger Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install       - Install all dependencies (Python + Node)"
	@echo ""
	@echo "Development:"
	@echo "  make dev          - Start both backend and frontend in dev mode"
	@echo "  make dev-backend  - Start backend only (Python FastAPI)"
	@echo "  make dev-frontend - Start frontend only (React dev server)"
	@echo ""
	@echo "Build:"
	@echo "  make build        - Build frontend for production"
	@echo "  make build-ui     - Alias for build"
	@echo ""
	@echo "Other:"
	@echo "  make clean        - Remove build artifacts and temp files"

# Install all dependencies
install:
	@echo "Setting up Python virtual environment..."
	@if [ ! -d .venv ]; then python -m venv .venv; fi
	@echo "Installing Python dependencies..."
	.venv/bin/pip install -r requirements.txt
	@echo ""
	@echo "Installing Node dependencies..."
	cd jaeger-ui && npm install
	@echo ""
	@echo "✓ All dependencies installed"

# Start both frontend and backend in development mode
# Note: This runs both in parallel - use Ctrl+C to stop both
dev:
	@echo "Starting Jaeger development environment..."
	@echo "Backend: http://localhost:8000"
	@echo "Frontend: http://localhost:5173"
	@echo ""
	@$(MAKE) -j2 dev-backend dev-frontend

# Start backend development server with auto-reload
dev-backend:
	@echo "Starting backend on http://localhost:8000"
	@if [ -f .venv/bin/uvicorn ]; then \
		.venv/bin/uvicorn app:app --reload --host 0.0.0.0 --port 8000; \
	else \
		uvicorn app:app --reload --host 0.0.0.0 --port 8000; \
	fi

# Start frontend development server
dev-frontend:
	@echo "Starting frontend on http://localhost:5173"
	cd jaeger-ui && npm start

# Build frontend for production
build:
	@echo "Building frontend for production..."
	cd jaeger-ui && npm run build
	@echo ""
	@echo "Copying build to dist/..."
	rm -rf dist
	cp -r jaeger-ui/packages/jaeger-ui/build dist
	@echo "✓ Frontend built to dist/"

build-ui: build

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf dist
	rm -rf jaeger-ui/packages/jaeger-ui/build
	rm -rf jaeger-ui/packages/plexus/lib
	rm -rf jaeger.db
	rm -rf __pycache__
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "✓ Cleaned"
