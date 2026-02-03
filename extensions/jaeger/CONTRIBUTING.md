# Development Guide

This guide shows you how to run the Jaeger extension locally for development.

## Quick Reference

```bash
# One-time setup
make install              # Install all dependencies

# Start development (choose one)
make dev                  # Use Make (recommended)
npm run dev              # Use npm (requires: npm install)
./dev.sh                 # Use shell script

# Individual services
make dev-backend         # Backend only
make dev-frontend        # Frontend only

# Production build
make build               # Build UI for production
```

## Prerequisites

- Python 3.10+
- Node.js 24+ (see jaeger-ui/.nvmrc)
- Make (optional, but recommended)

## Quick Start

### Option 1: Using Make (Recommended)

```bash
# Install all dependencies
make install

# Start both backend and frontend
make dev
```

The services will be available at:
- **Backend API**: http://localhost:8000
- **Frontend Dev Server**: http://localhost:5173

### Option 2: Using npm

```bash
# Install concurrently for running both servers
npm install

# Install all dependencies
npm run install:all

# Start both backend and frontend
npm run dev
```

### Option 3: Using Shell Script

```bash
# Install dependencies first
make install

# Start both servers
./dev.sh
```

### Option 4: Manual (Run in separate terminals)

**Terminal 1 - Backend:**
```bash
# Activate virtual environment
source .venv/bin/activate

# Install dependencies (if not already installed)
pip install -r requirements.txt

# Start backend
uvicorn app:app --reload --host 0.0.0.0 --port 8000

# Or without activating venv:
.venv/bin/uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend:**
```bash
# Navigate to frontend
cd jaeger-ui

# Install dependencies
npm install

# Start dev server
npm start
```

## Development Workflow

### Running Individual Services

Start only the backend:
```bash
make dev-backend
# or
npm run dev:backend
```

Start only the frontend:
```bash
make dev-frontend
# or
npm run dev:frontend
```

### Building for Production

Build the frontend:
```bash
make build
# or
npm run build
```

This creates an optimized production build in the `dist/` directory that the Python backend will serve.

### Testing the Full Stack

1. Start the development environment (`make dev`)
2. Open http://localhost:5173 in your browser
3. The frontend dev server proxies API requests to the backend at http://localhost:8000
4. To test with production build:
   ```bash
   make build
   make dev-backend
   # Open http://localhost:8000
   ```

## Development Tips

### Auto-reload

- **Backend**: Uvicorn watches for Python file changes and auto-reloads
- **Frontend**: Vite watches for React/TypeScript changes and hot-reloads

### API Endpoints

The backend exposes:
- `POST /v1/traces` - OTLP trace ingestion
- `GET /api/services` - List services
- `GET /api/traces` - Search traces
- `GET /api/traces/{traceId}` - Get specific trace
- `GET /api/config` - UI configuration
- `GET /api/health` - Health check

### Database

The backend uses SQLite (`jaeger.db` in the project root). To reset:
```bash
make clean
make dev-backend  # Will recreate the database
```

### Frontend Configuration

The frontend dev server is configured in `jaeger-ui/packages/jaeger-ui/vite.config.mts`. It proxies API requests to the backend at `http://localhost:8000` to avoid CORS issues.

## Troubleshooting

### Port already in use

If ports 8000 or 5173 are in use:
- Backend: Add `--port 8001` to the uvicorn command
- Frontend: Set `PORT=5174` before running `npm start`

### Frontend not connecting to backend

Make sure:
1. Backend is running on http://localhost:8000
2. Check the proxy configuration in `jaeger-ui/packages/jaeger-ui/vite.config.ts`
3. Check browser console for CORS or network errors

### Database issues

Remove and recreate:
```bash
rm jaeger.db
make dev-backend
```

## Project Structure

```
.
├── app.py                   # FastAPI backend entry point
├── database.py              # SQLAlchemy models
├── otlp_service.py         # OTLP trace ingestion
├── query_service.py        # Jaeger Query API
├── transformers.py         # Data format conversions
├── requirements.txt        # Python dependencies
├── jaeger-ui/             # React frontend (submodule)
│   └── packages/
│       └── jaeger-ui/     # Main UI package
└── dist/                  # Production build output
```

## Clean Up

Remove all build artifacts and databases:
```bash
make clean
# or
npm run clean
```
