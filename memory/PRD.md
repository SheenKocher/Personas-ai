# SynthTest — Synthetic User Testing Tool

## Problem Statement
Build a FastAPI + MongoDB backend with a React frontend for a synthetic-user testing tool. Data model with 4 Mongo collections (runs, steps, signals, persona_panels). Minimal React shell with persona grid, panel editor, reports placeholder, cross-stage diff placeholder, and a new run page.

## Architecture
- **Backend**: FastAPI on port 8001, MongoDB via motor, 4 collections with full CRUD endpoints
- **Frontend**: React (CRA) with Tailwind CSS, shadcn/ui components, dark theme
- **Database**: MongoDB (local), database name from DB_NAME env var
- **External services**: Browserbase (remote browser), Cloudinary (screenshot storage)

## User Personas
- Single-tenant demo app, no authentication
- Developer/QA engineer using the tool to configure synthetic user test runs

## Core Requirements
- [x] 4 MongoDB collections: runs, steps, signals, persona_panels
- [x] Full CRUD endpoints for each collection
- [x] Seed data with 5 personas (Priya, Arun, Meera, Devika, Farhan)
- [x] Live Grid page with persona tiles
- [x] Persona Panels page with create/edit/delete
- [x] New Run page with target/stage/panel selection
- [x] Reports placeholder page
- [x] Cross-Stage Diff placeholder page
- [x] Dark theme matching user's design system

## What's Been Implemented

### Phase 1 (2026-08-29)
- Backend: Full CRUD for runs, steps, signals, persona_panels with ObjectId validation
- Frontend: 5 pages (Live Grid, Persona Panels, New Run, Reports, Cross-Stage Diff)
- Seed data: 5 personas auto-seeded on startup
- Design: Dark theme with exact color palette per user spec
- Testing: 100% backend + 100% frontend pass rate

### Phase 2 — Spike (2026-08-29)
- Browserbase remote browser connection via Playwright CDP (connect_over_cdp)
- POST /api/spike/run endpoint: navigates to target URL, captures screenshot, extracts accessibility tree via CDP (Accessibility.getFullAXTree), captures console errors and failed network requests
- Screenshot upload to Cloudinary, URL stored in step document
- Results persisted as run + step documents in MongoDB
- Testing: 9/9 backend tests passed, verified with https://tier3.college (305 AX nodes, 4 console errors captured)

## Environment Variables
- MONGO_URL, DB_NAME, CORS_ORIGINS
- BROWSERBASE_API_KEY, BROWSERBASE_PROJECT_ID
- CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET

## Prioritized Backlog
### P0 (Done)
- Schema + CRUD + seed data + working skeleton
- Remote browser spike (Browserbase + Cloudinary)

### P1 (Next)
- Persona-driven agent loop replacing hardcoded spike
- Reports page logic (aggregate friction data)
- Cross-Stage Diff comparison view
- Run detail page with steps timeline

### P2
- Persona JSON editor in panel dialog
- Real-time run updates (WebSocket/polling)
- Friction heatmap visualization
- Export/import persona panels
