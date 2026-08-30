# SynthTest — Synthetic User Testing Tool

## Architecture
- Backend: FastAPI 8001, MongoDB, 7 modules
- Frontend: React CRA, Tailwind, shadcn/ui, dark theme, 9 pages
- External: Browserbase, Cloudinary, GPT-5, Stripe (test mode)
- Collections: runs, steps, signals, persona_panels, screen_graphs, payment_transactions

## Stripe Paywall
- First run free, subsequent runs require $1.00 test-mode payment
- POST /api/payments/checkout → Stripe checkout URL
- GET /api/payments/credits → {can_run, free_used, paid_credits}
- Webhook at POST /api/webhook/stripe
- PaywallGate component renders on /persona-panels and /prototype when blocked
- Tax mode: DIY (no tax help, cheapest). Available: Stripe-managed (full), Stripe-calculates-only, DIY.
