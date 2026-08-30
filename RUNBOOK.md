# SynthTest — Demo Runbook & Operations Guide

> Synthetic User Testing Tool — run AI-driven personas (including disability profiles)
> against a live website or a static prototype, then compare where they struggle.
>
> Branch: `feature/saloni` · Generated from a full codebase audit.

---

## 1. What this app does + architecture

**SynthTest** spins up a panel of synthetic test users ("personas") and drives each one
through a goal on your product — either the **live website** (runtime) or a **static
mockup flow** (prototype). Each persona has its own perception mode (full sight, screen
reader / AX-tree only, zoomed low-vision), allowed actions (e.g. keyboard-only users
can't `click`), a frustration budget, and tolerance rules. The system records every
step, screenshot, and friction signal, then ranks the worst screens and shows where the
**prototype → runtime** experience regressed.

### Core components
| Component | Files | What it does |
|---|---|---|
| **Persona engine (runtime)** | `backend/engine.py`, `backend/browser.py` | Perceive → Think (LLM) → Act loop against a **live URL** via a Browserbase remote browser (Playwright CDP). Captures screenshot, accessibility tree, console/network errors per step. |
| **Persona generator** | `backend/generator.py` | One LLM call turns a 1–2 sentence audience description into 3–5 distinct personas (with disability coverage + constraint enforcement). |
| **Prototype engine (mockup)** | `backend/prototype_engine.py` | Runs personas against a **mockup state graph** (screens + labeled transitions). Uses GPT-5 vision on the mockup image; screen-reader personas get a text-only description. |
| **Signals** | `backend/signals.py` | Derives friction/accessibility signals from a run and aggregates them by screen, weighted by frequency × severity. |
| **Cross-stage diff** | `backend/diff.py` | Compares prototype vs runtime signals for the same goal → regression report grouped by screen. |
| **Paywall** | `backend/paywall.py` | First run free; each subsequent run needs a $1.00 Stripe **test-mode** credit. |
| **Frontend** | `frontend/src` (React CRA + Tailwind + shadcn/ui, dark theme) | Pages: Live Grid, Persona Panels, Generate, Prototype Studio, New Run, Reports, Cross-Stage Diff, Payment. |
| **Data** | MongoDB | Collections: `runs`, `steps`, `signals`, `persona_panels`, `screen_graphs`, `payment_transactions`. IDs are Mongo ObjectIds returned as strings. |

Backend: FastAPI on `0.0.0.0:8001`, all routes prefixed `/api`.
Frontend: talks to the backend only via `REACT_APP_BACKEND_URL`.

---

## 2. Setup — API keys / env vars

Env files live at `backend/.env` and `frontend/.env` (both are git-ignored — recreate them
if the container is fresh).

### `backend/.env`
```
# --- Already configured (do NOT change) ---
MONGO_URL="mongodb://localhost:27017"
DB_NAME="synthtest_database"
CORS_ORIGINS="*"

# --- LLM: NO SETUP NEEDED ---
# All LLM calls (persona generation + reasoning + prototype vision) run through the
# built-in Emergent Universal Key. It is injected as EMERGENT_LLM_KEY.
# You do NOT need a separate OpenAI/Anthropic/Google account.
EMERGENT_LLM_KEY="<universal key — ask the platform / profile > Universal Key>"

# --- Required for RUNTIME runs (live-website testing) ---
BROWSERBASE_API_KEY="bb_live_..."        # https://www.browserbase.com → Settings → API Keys
BROWSERBASE_PROJECT_ID="..."             # Browserbase → Project → Settings
CLOUDINARY_CLOUD_NAME="..."              # https://cloudinary.com → Dashboard
CLOUDINARY_API_KEY="..."
CLOUDINARY_API_SECRET="..."

# --- Required only for the PAYWALL (2nd run onward) ---
STRIPE_API_KEY="sk_test_..."             # Stripe test-mode secret key
```

### `frontend/.env`
```
REACT_APP_BACKEND_URL=<your preview/deployed base URL>   # do NOT hardcode elsewhere
WDS_SOCKET_PORT=443
```

**Which keys unlock which flow**
- **Generate personas / any reasoning** → Universal Key (already handled). No setup.
- **Prototype run (mockup)** → Universal Key + Cloudinary (to host the uploaded mockup).
- **Runtime run (live URL)** → Browserbase + Cloudinary + Universal Key.
- **2nd run onward** → Stripe test key (else you get HTTP 402).

After editing `backend/.env`, restart the backend:
```
sudo supervisorctl restart backend
```

> ⚠️ Without `EMERGENT_LLM_KEY` / Browserbase / Cloudinary set, runs **do not error out
> loudly** — they silently degrade (the persona just "waits" and eventually "gives up").
> See §5. Always confirm keys are set before demoing.

---

## 3. Step-by-step demo instructions

### A. Pick or create a persona panel
1. Go to **Persona Panels**. A seed panel ("Seed panel …", `client_ref: seed-demo`) with 5
   personas (Rushed Professional, Keyboard-Only, Screen-Reader, Low-Vision, Low-Literacy)
   is already there.
2. To make your own: go to **Generate**, type an audience (e.g. *"Tier-2 city shopkeepers,
   35–55, low English literacy, budget Android, distrust upfront payment"*), set a count,
   click generate, review, and save it as a named panel.

### B. Runtime run (test a LIVE website)
1. Go to **New Run**.
2. **Target** = a live URL (e.g. `https://your-product.com`). **Goal** = a plain-English task
   (e.g. *"Complete the checkout flow"*).
3. Pick a **panel** (or a single persona) and **Start Run**.
4. Watch on **Live Grid** — but **refresh the page** to see progress (it is not auto-live;
   see §5).

### C. Prototype run (test a MOCKUP flow)
1. Go to **Prototype Studio**.
2. Add **screens** (name each, upload a mockup image → stored on Cloudinary).
3. Add **transitions** between screens (e.g. `Home --click Pricing--> Pricing`), set the
   **start screen**, and **save the graph**.
4. Choose a panel + goal, set concurrency, and **Run**.

### D. See results
- **Reports** — open a batch by ID (or run IDs) to see per-persona outcomes, steps,
  screenshots, and derived signals; and the aggregated **worst screens**.
- **Cross-Stage Diff** — enter the prototype batch/run IDs and the runtime batch/run IDs
  (or a shared goal) to see where runtime regressed vs the prototype, grouped by screen.

---

## 4. Reset / clear seed & demo data before a real run

The only seed marker is `client_ref: "seed-demo"` on a `persona_panels` doc.
**Nothing uses a `seeded: true` flag.** No seeded runs/steps/signals exist by default —
they only appear once you run. To wipe demo data:

```bash
# Clear all run artifacts (keeps your saved panels & graphs):
mongo synthtest_database --eval '
  db.runs.deleteMany({});
  db.steps.deleteMany({});
  db.signals.deleteMany({});
  db.payment_transactions.deleteMany({});   // also resets the "first run free" counter
'

# Remove the seed persona panel too (see the CAVEAT below):
mongo synthtest_database --eval 'db.persona_panels.deleteMany({ client_ref: "seed-demo" })'
```
> Use `mongosh` instead of `mongo` if that's what's installed.

**🔴 CAVEAT — the seed panel comes back.** `startup()` in `backend/server.py` re-inserts/
updates the seed panel **every time the backend starts or hot-reloads**. So deleting it is
not durable. If you truly need it gone during a real run, either:
- delete it and **do not restart** the backend, **or**
- temporarily comment out the seeder in `server.py` (`@app.on_event("startup")`) and restart.

**Free-credit note:** the paywall counts *every* row in `runs` (including any leftover
spike run). Clearing `runs` + `payment_transactions` resets you back to "first run free".

Optional cleanup of leftover dev dumps at repo root: `gen_result.json`, `engine_result.json`
(unused; safe to delete).

---

## 5. Known limitations & what NOT to click during a live demo

_All pulled directly from the audit of this branch._

1. **🔴 Live Grid is not real-time.** It fetches once on page load — there is no websocket
   or polling (`backend/ws_manager.py` exists but is **dead code**, never wired in). To see a
   run progress, **manually refresh Live Grid / Reports.** Don't tell judges it updates live.

2. **🔴 LLM failures fail silently.** In `engine.py` and `prototype_engine.py`, if the LLM
   call errors (missing/invalid Universal Key, rate limit, bad JSON), the code swallows it and
   makes the persona `wait`, then eventually `gives up`. It looks like a normal "gave up" run,
   not an error. **Before demoing, confirm at least one run produces real steps** — if every
   persona just "gives up" instantly, check `tail -f /var/log/supervisor/backend.err.log` for
   the real cause; the UI won't show it.

3. **🔴 Do NOT edit backend files mid-demo.** The backend runs with `--reload` and keeps
   in-progress runs as in-memory tasks. Any file save hot-reloads the server, **kills running
   tasks, and leaves runs stuck at `in_progress` ("Running") forever.**

4. **🔴 Do NOT call `/api/spike/run`.** It's a leftover spike endpoint (`backend/spike.py`),
   not wired into the UI. If hit, it (a) writes a junk empty-persona run into Live Grid/Reports
   and (b) **burns your free-run credit**. It also has a hardcoded `tier3.college` target.
   Best removed before judging.

5. **⚠️ Paywall kicks in on the 2nd run.** First run is free (global counter, not per-user);
   after that you get **HTTP 402** until a $1 Stripe test payment is made — and that requires a
   real `STRIPE_API_KEY` (the code otherwise falls back to a fake `sk_test_emergent` key that
   fails). Plan your demo to either (a) do one run, (b) pre-load a paid credit, or
   (c) clear `runs` + `payment_transactions` between runs (§4).

6. **⚠️ Screen-reader tiles show a fake AX-tree snippet.** The `<main role="main">…` block on
   Live Grid (`LiveGrid.jsx`) is a **static placeholder**, not live run output. Don't present
   it as real data.

7. **⚠️ Prototype vision needs a public mockup URL.** If a mockup image can't be downloaded,
   the persona proceeds with "(image could not be loaded)" instead of failing — so make sure
   Cloudinary uploads succeed before running.

8. **⚠️ Cross-Stage Diff needs matching IDs.** It only produces output when you give it valid
   prototype + runtime batch/run IDs (or a shared goal that both stages actually ran). Run
   both stages first, copy the batch IDs from Reports.

**Safe happy-path for judges:** set keys → Generate (or use seed) panel → one Prototype run
→ view Reports → one Runtime run on the same goal → view Reports → Cross-Stage Diff. Refresh
pages to see progress. Don't touch code, don't hit spike, keep it to the credits you have.

---

## 6. Deployed URL & redeploy

- **Preview URL:** `https://9029a9de-8419-428d-a72b-dbf3cd7e5649.preview.emergentagent.com`
- **Deployed URL:** _(fill in after you deploy — use the "Deploy" button in the Emergent UI)_

### If something breaks right before judging
1. **Quick restart (most issues):**
   ```
   sudo supervisorctl restart backend frontend
   sudo supervisorctl status
   ```
2. **Backend won't start / 502s:** check `tail -n 50 /var/log/supervisor/backend.err.log`.
   Most common cause = a missing env var in `backend/.env` (`MONGO_URL`, `DB_NAME`, or a key).
3. **Every run instantly "gives up":** almost always a missing/invalid `EMERGENT_LLM_KEY`,
   Browserbase, or Cloudinary key — the error is only in the backend log (§5.2).
4. **Runs stuck at "Running" forever:** a hot-reload killed the task — restart the backend and
   re-run; clear stuck rows with `db.runs.updateMany({outcome:"in_progress"},{$set:{outcome:"gave_up"}})`.
5. **Redeploy:** use the platform **Deploy** button to ship the latest commit. To publish code
   changes first, use **Save to GitHub** in the chat, then redeploy.

> Note: do not run `git` write commands manually here — use **Save to GitHub** in the chat UI.
