# SynthTest — Synthetic User Testing Tool

## Problem Statement
Build a FastAPI + MongoDB backend with a React frontend for a synthetic-user testing tool with persona engine, signal derivation, and cross-persona aggregation.

## Architecture
- **Backend**: FastAPI on port 8001, MongoDB via motor
- **Frontend**: React (CRA) with Tailwind CSS, shadcn/ui, dark control-room theme
- **External services**: Browserbase (remote browser), Cloudinary (screenshots), OpenAI GPT-5 via Emergent LLM key
- **Modules**: browser.py (CDP), engine.py (agent loop), signals.py (derivation + aggregation)

## What's Been Implemented

### Phase 1 — Schema + CRUD + UI
- 4 MongoDB collections with full CRUD, seed data (7 personas), 5 frontend pages

### Phase 2 — Browserbase Spike
- Remote browser via CDP, Cloudinary upload

### Phase 3 — Persona Engine
- Stage-agnostic agent loop: perceive → think (GPT-5) → act → record → repeat
- Background execution with polling (202 Accepted)

### Phase 4 — Parallel Orchestrator + Disability Personas
- POST /api/engine/run-panel: runs N personas concurrently (max 3)
- Keyboard-only (motor) + screen-reader (blind) personas
- Server-side action enforcement with 8/8 unit tests

### Phase 5 — Signal Derivation + Aggregation
- **Objective signals**: console errors (sev by type), failed requests (sev: 5xx=4, 404=3, 4xx=2)
- **Behavioral signals**: state revisits (sev 2/3), excessive path length, dead-clicks, keyboard dead-ends (motor-only, 2+ consecutive key presses stuck)
- `POST /api/signals/derive/{run_id}`: manual derivation trigger
- `GET /api/signals/aggregate?batch_id=X`: ranked worst screens, weighted by frequency × severity
- Signal sources: console_error, failed_request, state_revisit, path_length, dead_click, keyboard_dead_end, action_rejected, persona_report, frustration_budget
- Verified: /pricing ranked #1 worst screen (score 89.0), keyboard dead-end detected for Arun
- 13/13 tests passing

## Test Results Summary
- Phase 1-5: 55+ tests total, all passing
- Key verified: aggregation correctly ranks /pricing as worst screen across all personas in batch

## Prioritized Backlog
### P1 (Next)
- Wire engine + aggregation to frontend (run detail page, signal dashboard)
- Reports page: render aggregation results as ranked screen cards
- Cross-Stage Diff: compare prototype vs runtime signal aggregations

### P2
- Real-time run progress via SSE/WebSocket
- Concurrent panel runs with 5+ personas
- Friction heatmap visualization
- Export signals as CSV/JSON report
