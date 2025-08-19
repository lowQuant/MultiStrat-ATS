# MultiStrat-ATS (MATS)

Multi-strategy Automated Trading System. Orchestrate, run, and monitor multiple automated trading strategies concurrently with broker-agnostic execution.

- Backend: FastAPI (async), ib_async (Interactive Brokers), extensible to other brokers (e.g., Alpaca).
- Frontend: React + TypeScript + Vite + shadcn/ui.
- Architecture: Strategy manager, isolated strategy runtimes, WebSocket log/metrics streaming.

## Features
- Multi-strategy orchestration with isolation (unique client/session IDs)
- Async broker connectivity (ib_async), pluggable adapters
- Start/stop strategies, config profiles, lifecycle management
- Real-time logs and status via WebSockets
- Extensible portfolio/risk modules

## Quick Start
```bash
# Backend
uvicorn backend.main:app --reload

# Frontend
cd frontend && pnpm install && pnpm dev
```

## Packages
- Python: `mats_core`
- Frontend app: `mats-ui`
- Docker: `ghcr.io/<you>/multistrat-ats`

## Roadmap
- Strategy management (per-strategy threads/async tasks)
- Portfolio & risk management
- Order routing & execution abstraction
- Analytics & reporting

## License
MIT
