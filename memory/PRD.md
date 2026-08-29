# SynthTest — Synthetic User Testing Tool

## Architecture
- **Backend**: FastAPI on port 8001, MongoDB via motor, 5+ modules
- **Frontend**: React (CRA), Tailwind CSS, shadcn/ui, dark control-room theme
- **External**: Browserbase (remote browser), Cloudinary (screenshots/mockups), GPT-5 via Emergent LLM key (text + vision)
- **Modules**: browser.py, engine.py, prototype_engine.py, signals.py, generator.py, ws_manager.py

## Collections
runs, steps, signals, persona_panels, screen_graphs

## What's Been Implemented
1. Schema + CRUD + UI (4 collections, 5 pages, seed data)
2. Browserbase spike (remote browser CDP, Cloudinary)
3. Persona engine (perceive→think→act→record, GPT-5, background with polling)
4. Parallel orchestrator (asyncio.gather, 3 concurrent, disability personas)
5. Signal derivation (objective: console/network errors; behavioral: revisits, path length, dead-clicks, keyboard dead-ends)
6. Aggregation endpoint (weighted score by screen)
7. Persona generator (LLM-powered, editable cards UI)
8. Panel editor redesign (inline-editable cards, constraint summaries, action chips)
9. **Prototype stage** (NEW):
   - Screen graph model: screens (id, name, image_url) + transitions (from, label, to)
   - GPT-5 vision: analyzes mockup images via ImageContent
   - Intent-based actions matched against labeled transitions
   - Dead-ends = friction signals (like 404 in runtime)
   - stage=prototype runs with SAME schema as runtime
   - Upload mockup → Cloudinary, CRUD for graphs
   - Prototype Studio UI: screen cards with upload zones, transition editor, run config

## Test Results: 14/14 backend + 100% frontend (iteration 8)
## Total: 70+ tests across all iterations

## Prioritized Backlog
### P1 (Next)
- Wire WebSocket to broadcast step updates for live grid
- Cross-Stage Diff: compare prototype vs runtime signal aggregations
- Reports page: render aggregation data

### P2
- Real-time grid with live screenshot updates
- Concurrent 5+ personas
- Export signals/reports as CSV
