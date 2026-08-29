# SynthTest — Synthetic User Testing Tool

## Problem Statement
Build a FastAPI + MongoDB backend with a React frontend for a synthetic-user testing tool. Persona engine with agent loop, parallel multi-persona orchestrator, disability persona enforcement.

## Architecture
- **Backend**: FastAPI on port 8001, MongoDB via motor
- **Frontend**: React (CRA) with Tailwind CSS, shadcn/ui, dark control-room theme
- **External services**: Browserbase (remote browser), Cloudinary (screenshots), OpenAI GPT-5 via Emergent LLM key
- **Agent loop**: BrowserSession (browser.py) → PersonaEngine (engine.py) → async background tasks
- **Parallel orchestrator**: asyncio.gather for concurrent persona runs (up to 3)

## Environment Variables
- MONGO_URL, DB_NAME, CORS_ORIGINS
- BROWSERBASE_API_KEY, BROWSERBASE_PROJECT_ID
- CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
- OPENAI_API_KEY, EMERGENT_LLM_KEY

## What's Been Implemented

### Phase 1 — Schema + CRUD + UI
- 4 MongoDB collections with full CRUD, seed data, 5 frontend pages

### Phase 2 — Browserbase Spike
- Remote browser via CDP, Cloudinary upload, POST /api/spike/run

### Phase 3 — Persona Engine
- Stage-agnostic agent loop: perceive → think (GPT-5) → act → record → repeat
- Background execution with polling pattern

### Phase 4 — Parallel Orchestrator + Disability Personas
- POST /api/engine/run-panel: runs N personas concurrently (max 3)
- GET /api/engine/batch/{batch_id}: poll batch status with per-persona results
- Disability personas:
  - Arun (motor): keyboard-only, NO click in allowed_actions
  - Meera (blind): ax_tree_only perception, click IS allowed
- Server-side enforcement: actions not in allowed_actions are rejected, logged as behavioral signals, overridden to wait, frustration increased
- 8/8 unit tests prove rejection logic works
- Real parallel run verified: 3 personas (Priya, Arun, Meera) ran concurrently, each with own Browserbase session
- Batch cleanup on shutdown

## Test Results
- Phase 1: 8/8 backend + 100% frontend
- Phase 2: 9/9 backend (spike)
- Phase 3: 12/12 backend (engine)
- Phase 4: 8/9 integration + 8/8 unit = 16/17 (1 "failure" = GPT-5 too smart to trigger rejection at runtime)
- Total: 45+ tests passing

## Prioritized Backlog
### P1 (Next)
- Wire engine to frontend "New Run" page with polling progress UI
- Run detail page with step timeline + screenshot viewer
- Reports page: aggregate friction signals across runs
- Cross-Stage Diff: compare prototype vs runtime signals

### P2
- Real-time run progress via SSE/WebSocket
- Concurrent panel runs with 5+ personas
- Friction heatmap visualization
- Export/import persona panels
