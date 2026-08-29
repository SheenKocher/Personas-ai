# SynthTest — Synthetic User Testing Tool

## Problem Statement
Build a FastAPI + MongoDB backend with a React frontend for a synthetic-user testing tool. Data model with 4 Mongo collections (runs, steps, signals, persona_panels). Minimal React shell with persona grid, panel editor, reports placeholder, cross-stage diff placeholder, and a new run page.

## Architecture
- **Backend**: FastAPI on port 8001, MongoDB via motor, 4 collections with full CRUD endpoints
- **Frontend**: React (CRA) with Tailwind CSS, shadcn/ui components, dark theme
- **Database**: MongoDB (local), database name from DB_NAME env var

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

## What's Been Implemented (2026-08-29)
- Backend: Full CRUD for runs, steps, signals, persona_panels with ObjectId validation
- Frontend: 5 pages (Live Grid, Persona Panels, New Run, Reports, Cross-Stage Diff)
- Seed data: 5 personas auto-seeded on startup
- Design: Dark theme with exact color palette per user spec
- Meera (screen reader) tile shows AX-tree transcript
- Testing: 100% backend + 100% frontend pass rate

## Prioritized Backlog
### P0 (Done)
- Schema + CRUD + seed data + working skeleton

### P1 (Next)
- Reports page logic (aggregate friction data)
- Cross-Stage Diff comparison view
- Run detail page with steps timeline
- Step viewer with screenshots

### P2
- Persona JSON editor in panel dialog
- Real-time run updates (WebSocket/polling)
- Friction heatmap visualization
- Export/import persona panels
