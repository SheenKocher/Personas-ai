# SynthTest — Synthetic User Testing Tool

## Architecture
- Backend: FastAPI 8001, MongoDB, 6 modules (server, engine, prototype_engine, signals, diff, generator, browser, ws_manager)
- Frontend: React CRA, Tailwind, shadcn/ui, dark theme, 7 pages
- External: Browserbase (CDP), Cloudinary, GPT-5 (Emergent LLM key)
- Collections: runs, steps, signals, persona_panels, screen_graphs

## Pages
1. Live Grid (/) — persona tiles, recent runs, loading/error/empty states
2. Persona Panels (/persona-panels) — inline editor, generate, auto-save, constraint summaries
3. Generate (/generate-panel) — audience→LLM→editable cards→save
4. Prototype Studio (/prototype) — screen graph builder, mockup upload, run config with polling timeout
5. Reports (/reports) — signal aggregation by batch, recent batches, ranked screens
6. Cross-Stage Diff (/cross-stage-diff) — regression report, prototype vs runtime, per-screen verdicts
7. New Run (/new-run) — manual run creation form

## Hardening (latest iteration)
- All pages: Spinner/ErrorBanner/EmptyState shared components
- Error toasts on all catch blocks (save/delete/generate/fetch)
- Polling cleanup on unmount + 30-poll timeout (PrototypeStudio)
- Consistent label styling (11px uppercase tracking-wider)
- Reports page: functional (no longer placeholder)
- 100% backend + 100% frontend verification (iteration 9)
