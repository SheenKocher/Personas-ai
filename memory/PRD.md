# SynthTest — Synthetic User Testing Tool

## Problem Statement
Build a FastAPI + MongoDB backend with a React frontend for a synthetic-user testing tool. Data model with 4 Mongo collections (runs, steps, signals, persona_panels). Persona engine with agent loop: perceive → think → act → record.

## Architecture
- **Backend**: FastAPI on port 8001, MongoDB via motor
- **Frontend**: React (CRA) with Tailwind CSS, shadcn/ui, dark control-room theme
- **External services**: Browserbase (remote browser), Cloudinary (screenshots), OpenAI GPT-5 via Emergent LLM key
- **Agent loop**: BrowserSession (browser.py) → PersonaEngine (engine.py) → async background tasks

## Environment Variables
- MONGO_URL, DB_NAME, CORS_ORIGINS
- BROWSERBASE_API_KEY, BROWSERBASE_PROJECT_ID
- CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
- OPENAI_API_KEY, EMERGENT_LLM_KEY

## What's Been Implemented

### Phase 1 — Schema + CRUD + UI (2026-08-29)
- 4 MongoDB collections with full CRUD, seed data, 5 frontend pages

### Phase 2 — Browserbase Spike (2026-08-29)
- Remote browser via CDP, Cloudinary upload, POST /api/spike/run

### Phase 3 — Persona Engine (2026-08-29)
- Stage-agnostic agent loop: perceive → think (GPT-5) → act → record → repeat
- POST /api/engine/run: starts run in background, returns 202 with run_id
- GET /api/engine/run/{run_id}: poll for results (steps, signals, outcome)
- Action validation: rejects actions not in persona's allowed_actions
- Frustration tracking with budget-based termination
- Signal generation: friction reports + behavioral signals
- Structured errors: 502 upstream, 504 timeouts
- Browserbase session always released (BrowserSession context manager)
- Shutdown hook marks orphaned runs as gave_up
- Verified: 12-step run on tier3.college with pricing discovery goal

## Test Results
- Phase 1: 8/8 backend + 100% frontend
- Phase 2: 9/9 backend (spike)
- Phase 3: 12/12 backend (engine)
- Total verified: 29/29 tests passing

## Prioritized Backlog
### P1 (Next)
- Wire engine to frontend "New Run" page with polling UI
- Run detail page with step timeline + screenshot viewer
- Reports page: aggregate friction signals across runs
- Cross-Stage Diff: compare prototype vs runtime signals

### P2
- Persona JSON editor in panel dialog
- Real-time run progress (WebSocket or SSE instead of polling)
- Concurrent persona runs (run all panel personas in parallel)
- Friction heatmap visualization
