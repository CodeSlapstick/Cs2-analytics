# Project Context: CS2 Analytics & Scouting Platform

## Architecture & Tech Stack
- Backend: FastAPI (Python 3.12), SQLAlchemy, Alembic, PostgreSQL (Docker Compose)
- Frontend: React 18, TypeScript, Vite, Tailwind/CSS
- Parser & Data: Demoparser, CS2 demo files (.dem), JSON outputs stored in `output/json/`
- Spatial & Analytics: Coordinate mapping for radar/heatmaps (13 CS2 maps), Grid clustering

## Key Directories & Roles
- `backend/app.py`: Main API routes and FastAPI initialization
- `backend/models.py`: Database schema definitions (SQLAlchemy)
- `backend/etl_loader.py`: Script for loading parsed JSON demo data into PostgreSQL
- `backend/alembic/`: Database migrations
- `frontend/src/`: React pages (`HeatmapPage.tsx`, `EconomyPage.tsx`, `MatchPage.tsx`, `RoundPage.tsx`, `AnalysisPage.tsx`)
- `frontend/src/api.ts`: Frontend API client
- `assets/maps/` & `assets/radars.json`: Radar map assets and coordinate boundaries
- `output/json/`: Parsed CS2 demo JSON files

## Rules for AI Agent
1. Always check existing patterns in `backend/app.py` and `frontend/src/` before creating new logic.
2. Maintain strict typing in TypeScript.
3. Do not scan or modify `node_modules/`, `venv/`, or `.dem` files.
