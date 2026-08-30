# Local Setup — Running SynthTest Locally

Run the **SynthTest** synthetic-user-testing app on your own machine.
Stack: **FastAPI (Python 3.11)** backend · **React (CRA/craco, Node 20, yarn)** frontend · **MongoDB**.

Branch: `feature/saloni`

---

## 0. Prerequisites (install once)

- **Python 3.11+**
- **Node.js 20+**
- **Yarn** — `npm install -g yarn`
- **MongoDB** running locally. Either install MongoDB Community Server, or run it in Docker:
  ```bash
  docker run -d --name mongo -p 27017:27017 mongo:7
  ```
- **VS Code** (recommended) with the *Python* and *ES7+ React* extensions.

> The browser automation connects to a **remote Browserbase** browser over CDP,
> so you do NOT need a local Chromium or `playwright install`.

---

## 1. Get the code

```bash
git clone <your-repo-url>
cd <repo>
git checkout feature/saloni
code .            # open in VS Code
```

You will run **two terminals** in VS Code — one for the backend, one for the frontend.

---

## 2. Backend — `/backend`

```bash
cd backend

# create + activate a virtual environment
python3 -m venv venv
source venv/bin/activate            # Windows: venv\Scripts\activate

# emergentintegrations is NOT on public PyPI — install it from the Emergent index first:
pip install emergentintegrations --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/

# then the rest of the dependencies
pip install -r requirements.txt
```

### Create `backend/.env`

This file is **git-ignored**, so it does NOT come with the repo — you must create it.

```env
# --- Database (required) ---
MONGO_URL="mongodb://localhost:27017"
DB_NAME="synthtest_database"
CORS_ORIGINS="*"

# --- LLM via Emergent Universal Key (required for persona reasoning/generation) ---
EMERGENT_LLM_KEY="sk-emergent-23659Be041bD147051"

# --- Browserbase (required for RUNTIME / live-website runs) ---
BROWSERBASE_API_KEY="bb_live_21r75dqpZ7n2LmVH7SVlRXJKnDY"
BROWSERBASE_PROJECT_ID="a7ae8cd2-d62e-423c-ac05-a8484adca5f2"

# --- Cloudinary (required to store screenshots / mockups) ---
CLOUDINARY_CLOUD_NAME="ca583u55"
CLOUDINARY_API_KEY="455748796712688"
CLOUDINARY_API_SECRET="5fucOhEiw8vyM47EbIqywvRpLcQ"

# --- Stripe (optional — only needed for the 2nd-run-onward paywall) ---
# STRIPE_API_KEY="sk_test_..."
```

### Start the backend (port 8001)

```bash
uvicorn server:app --host 0.0.0.0 --port 8001 --reload
```

Verify: open <http://localhost:8001/api/> → should return
`{"message":"Synthetic User Testing API"}`.
On startup the backend auto-seeds a demo persona panel.

---

## 3. Frontend — `/frontend`

Open a **second** terminal:

```bash
cd frontend
yarn install
```

### Create `frontend/.env`

Also git-ignored — create it. For local dev, point it at your local backend:

```env
REACT_APP_BACKEND_URL=http://localhost:8001
```

> ⚠️ The app calls `${REACT_APP_BACKEND_URL}/api/...` internally.
> Do **not** append `/api` here.

### Start the frontend (port 3000)

```bash
yarn start
```

Opens <http://localhost:3000>.

---

## 4. You're running

| Service  | URL                              |
|----------|----------------------------------|
| Frontend | http://localhost:3000            |
| Backend  | http://localhost:8001/api        |
| MongoDB  | mongodb://localhost:27017        |

The Live Grid will immediately show the 5 seeded personas. Create a panel
(or use the seed), set a target + goal on **New Run**, start a run, then check
**Reports** for the aggregated friction analysis.

---

## 5. Quick smoke tests

```bash
# API is up
curl http://localhost:8001/api/health          # {"status":"ok"}

# Run-credit status (first run is free)
curl http://localhost:8001/api/payments/credits

# LLM works (returns 3 personas; takes a few seconds)
curl -X POST http://localhost:8001/api/generate-personas \
  -H "Content-Type: application/json" \
  -d '{"audience_description":"budget travelers on mobile","count":3}'
```

---

## 6. Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `KeyError: 'MONGO_URL'` on backend start | `backend/.env` is missing or not created. |
| `emergentintegrations` fails to install | You skipped the `--extra-index-url ...` step (it's not on public PyPI). |
| Frontend loads but all API calls fail / CORS errors | `REACT_APP_BACKEND_URL` wrong, or backend not running on 8001. Restart `yarn start` after editing `.env` (CRA reads env only at startup). |
| `MongoNetworkError` / connection refused | MongoDB isn't running — start the service/Docker container. |
| Runs instantly show "gave up" with **zero steps** | A key in `backend/.env` is missing/invalid. The real error is printed **only in the backend terminal** (known silent-failure design). |
| Port already in use | Something else is on 8001/3000 — stop it, or change the port (backend `--port`, frontend `PORT=3001 yarn start`). |

---

## 7. Notes & limitations (for a demo)

- **Live Grid is not real-time** — it fetches once on load; refresh to see run updates.
- **No in-app browser view** — the agent runs on a remote Browserbase browser. To watch a
  session live, use the **Browserbase dashboard** (Sessions → live view / recording).
- **Per-step screenshots/reasoning are stored but not shown in the UI** yet — they're
  available via `GET /api/engine/run/{run_id}` and the `steps` collection.
- **Paywall:** first run is free (global counter); each subsequent run needs a $1 Stripe
  test credit (requires `STRIPE_API_KEY`).
- **Do not call `/api/spike/run`** — leftover spike endpoint; it writes junk runs and burns
  the free credit.

See `RUNBOOK.md` for the full architecture overview, demo script, and audit findings.
