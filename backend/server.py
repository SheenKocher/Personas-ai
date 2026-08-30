from fastapi import FastAPI, APIRouter, HTTPException, Query, UploadFile, File as FastAPIFile, WebSocket, WebSocketDisconnect
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict, BeforeValidator
from typing import List, Optional, Any, Annotated
from datetime import datetime, timezone
from bson import ObjectId
from enum import Enum
from bson.errors import InvalidId

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from ws_manager import broadcaster

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# --- PyObjectId & BaseDocument ---

def validate_object_id(v: Any) -> str:
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str):
        return v
    raise ValueError(f"Invalid ObjectId: {v}")

PyObjectId = Annotated[str, BeforeValidator(validate_object_id)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: dict):
        if doc is None:
            return None
        return cls(**doc)

    def to_mongo(self) -> dict:
        d = self.model_dump(by_alias=True, exclude_none=True)
        d.pop("_id", None)
        return d


# --- Enums ---

class StageEnum(str, Enum):
    prototype = "prototype"
    runtime = "runtime"

class OutcomeEnum(str, Enum):
    success = "success"
    gave_up = "gave_up"
    max_steps = "max_steps"
    in_progress = "in_progress"

class SignalTypeEnum(str, Enum):
    objective = "objective"
    behavioral = "behavioral"
    reported = "reported"

class CompositionEnum(str, Enum):
    broad = "broad"
    focused = "focused"


# --- Document Models ---

class Run(BaseDocument):
    stage: StageEnum
    persona: dict = Field(default_factory=dict)
    target: str = ""
    goal: str = ""
    outcome: OutcomeEnum = OutcomeEnum.in_progress
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    batch_id: Optional[str] = None
    browserbase_session_id: Optional[str] = None
    error: Optional[str] = None

class RunCreate(BaseModel):
    stage: StageEnum
    persona: dict = Field(default_factory=dict)
    target: str = ""
    goal: str = ""
    outcome: OutcomeEnum = OutcomeEnum.in_progress

class RunUpdate(BaseModel):
    stage: Optional[StageEnum] = None
    persona: Optional[dict] = None
    target: Optional[str] = None
    goal: Optional[str] = None
    outcome: Optional[OutcomeEnum] = None
    ended_at: Optional[str] = None


class Step(BaseDocument):
    run_id: str
    index: int = 0
    action: dict = Field(default_factory=dict)
    reasoning: str = ""
    screenshot_before_url: Optional[str] = None
    screenshot_after_url: Optional[str] = None
    location: Optional[str] = None
    timestamp: Optional[str] = None

class StepCreate(BaseModel):
    run_id: str
    index: int = 0
    action: dict = Field(default_factory=dict)
    reasoning: str = ""
    screenshot_before_url: Optional[str] = None
    screenshot_after_url: Optional[str] = None
    location: Optional[str] = None


class Signal(BaseDocument):
    run_id: str
    stage: StageEnum
    type: SignalTypeEnum
    severity: int = Field(ge=1, le=5)
    screen: str = ""
    description: str = ""
    source: Optional[str] = None
    count: Optional[int] = 1

class SignalCreate(BaseModel):
    run_id: str
    stage: StageEnum
    type: SignalTypeEnum
    severity: int = Field(ge=1, le=5)
    screen: str = ""
    description: str = ""
    source: Optional[str] = None


class PersonaPanel(BaseDocument):
    client_ref: str = ""
    audience_description: str = ""
    personas: list = Field(default_factory=list)
    composition: CompositionEnum = CompositionEnum.broad

class PersonaPanelCreate(BaseModel):
    client_ref: str = ""
    audience_description: str = ""
    personas: list = Field(default_factory=list)
    composition: CompositionEnum = CompositionEnum.broad

class PersonaPanelUpdate(BaseModel):
    client_ref: Optional[str] = None
    audience_description: Optional[str] = None
    personas: Optional[list] = None
    composition: Optional[CompositionEnum] = None


# --- App & Router ---

app = FastAPI()
api_router = APIRouter(prefix="/api")


# --- Health ---

@api_router.get("/")
async def root():
    return {"message": "Synthetic User Testing API"}

@api_router.get("/health")
async def health():
    return {"status": "ok"}


# --- Payments / Paywall ---

from starlette.requests import Request

@api_router.get("/payments/credits")
async def get_credits():
    from paywall import check_run_credits
    return await check_run_credits(db)

class PaymentCheckoutRequest(BaseModel):
    origin_url: str

@api_router.post("/payments/checkout")
async def create_payment_checkout(body: PaymentCheckoutRequest, request: Request):
    from paywall import get_stripe_checkout, RUN_PRICE
    host_url = str(request.base_url)
    webhook_url = f"{host_url}api/webhook/stripe"
    sc = get_stripe_checkout(webhook_url)
    req = CheckoutSessionRequest(
        amount=RUN_PRICE,
        currency="usd",
        success_url=f"{body.origin_url}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{body.origin_url}/payment/cancel",
        metadata={"type": "run_credit"},
    )
    session = await sc.create_checkout_session(req)
    # Record transaction before redirect
    await db.payment_transactions.insert_one({
        "session_id": session.session_id,
        "amount": RUN_PRICE,
        "currency": "usd",
        "status": "initiated",
        "payment_status": "pending",
        "credit_used": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"checkout_url": session.url, "session_id": session.session_id}

@api_router.get("/payments/status/{session_id}")
async def get_payment_status(session_id: str, request: Request):
    record = await db.payment_transactions.find_one({"session_id": session_id})
    if not record:
        raise HTTPException(404, "Transaction not found")
    # Poll Stripe directly if still pending
    if record.get("payment_status") != "paid":
        from paywall import get_stripe_checkout
        host_url = str(request.base_url)
        sc = get_stripe_checkout(f"{host_url}api/webhook/stripe")
        try:
            status = await sc.get_checkout_status(session_id)
            if status.payment_status == "paid":
                await db.payment_transactions.update_one(
                    {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                    {"$set": {"status": "completed", "payment_status": "paid",
                              "updated_at": datetime.now(timezone.utc).isoformat()}},
                )
                record = await db.payment_transactions.find_one({"session_id": session_id})
        except Exception:
            pass
    return {
        "session_id": record["session_id"],
        "status": record.get("status"),
        "payment_status": record.get("payment_status"),
    }

from emergentintegrations.payments.stripe.checkout import CheckoutSessionRequest

@api_router.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    from paywall import get_stripe_checkout
    host_url = str(request.base_url)
    sc = get_stripe_checkout(f"{host_url}api/webhook/stripe")
    body_bytes = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = await sc.handle_webhook(body_bytes, sig)
    except Exception as e:
        logger.warning("Webhook verification failed: %s", e)
        raise HTTPException(400, "Invalid webhook")
    if event.payment_status == "paid":
        await db.payment_transactions.update_one(
            {"session_id": event.session_id, "payment_status": {"$ne": "paid"}},
            {"$set": {"status": "completed", "payment_status": "paid",
                      "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
    return {"status": "ok"}


# --- Spike: Remote Browser Test ---

class SpikeRunRequest(BaseModel):
    target_url: str = "https://tier3.college"

@api_router.post("/spike/run")
async def spike_run(body: SpikeRunRequest):
    from spike import execute_spike_run
    try:
        result = await execute_spike_run(db, target_url=body.target_url)
        return result
    except Exception as e:
        logger.exception("Spike run failed")
        raise HTTPException(500, detail=str(e))


# --- Persona Engine ---

class EngineRunRequest(BaseModel):
    target_url: str = "https://tier3.college"
    goal: str = "Find the pricing page"
    stage: StageEnum = StageEnum.prototype
    persona: Optional[dict] = None
    persona_panel_id: Optional[str] = None
    persona_index: int = 0

# Background task storage for running engines
import asyncio as _asyncio
_engine_tasks: dict = {}  # run_id -> asyncio.Task

# Hard ceiling for a single engine run. 15 steps * (LLM call + browser actions +
# screenshot uploads) — if it exceeds this, something is hung (LLM/CDP with no
# timeout) and the run must be force-finalized so it can't show "Running" forever.
ENGINE_RUN_TIMEOUT_S = 1200


async def _mark_run_gave_up(run_id: str, reason: str):
    try:
        from bson import ObjectId as OID
        await db.runs.update_one(
            {"_id": OID(run_id), "outcome": "in_progress"},
            {"$set": {"outcome": "gave_up",
                      "ended_at": datetime.now(timezone.utc).isoformat(),
                      "error": reason}},
        )
    except Exception:
        logger.exception("Failed to mark run %s as gave_up", run_id)


async def _run_engine_background(run_id: str, target_url: str, goal: str, persona: dict, stage: str):
    """Background wrapper that catches all errors and ALWAYS finalizes the run."""
    from engine import run_persona_engine
    try:
        return await _asyncio.wait_for(
            run_persona_engine(
                db=db,
                target_url=target_url,
                goal=goal,
                persona=persona,
                stage=stage,
                existing_run_id=run_id,
            ),
            timeout=ENGINE_RUN_TIMEOUT_S,
        )
    except _asyncio.TimeoutError:
        logger.error("Engine run %s timed out after %ss — force-finalizing", run_id, ENGINE_RUN_TIMEOUT_S)
        await _mark_run_gave_up(run_id, f"Timed out after {ENGINE_RUN_TIMEOUT_S}s")
        return {"run_id": run_id, "outcome": "gave_up", "error": "timeout"}
    except _asyncio.CancelledError:
        # Task cancelled (server shutdown / hot-reload). CancelledError is a
        # BaseException, so a bare `except Exception` would miss it.
        logger.warning("Engine run %s cancelled — marking gave_up", run_id)
        await _mark_run_gave_up(run_id, "Cancelled (backend restart/shutdown)")
        raise
    except Exception as e:
        logger.exception("Background engine run failed for %s", run_id)
        await _mark_run_gave_up(run_id, str(e)[:500])
        return {"run_id": run_id, "outcome": "gave_up", "error": str(e)}
    finally:
        _engine_tasks.pop(run_id, None)

from starlette.responses import JSONResponse

@api_router.post("/engine/run")
async def engine_run(body: EngineRunRequest):
    from engine import run_persona_engine
    from browser import BrowserUpstreamError, BrowserTimeoutError
    from paywall import consume_credit

    # Paywall check
    if not await consume_credit(db):
        raise HTTPException(402, "Payment required. Purchase a run credit first.")

    # Resolve persona
    persona = body.persona
    if not persona and body.persona_panel_id:
        try:
            panel_doc = await db.persona_panels.find_one({"_id": ObjectId(body.persona_panel_id)})
        except Exception:
            raise HTTPException(400, "Invalid persona_panel_id")
        if not panel_doc:
            raise HTTPException(404, "Persona panel not found")
        personas = panel_doc.get("personas", [])
        if body.persona_index >= len(personas):
            raise HTTPException(400, f"persona_index {body.persona_index} out of range (panel has {len(personas)} personas)")
        persona = personas[body.persona_index]

    if not persona:
        seed = await db.persona_panels.find_one({"client_ref": "seed-demo"})
        if seed and seed.get("personas"):
            persona = seed["personas"][0]
        else:
            raise HTTPException(400, "No persona provided and no seed panel found")

    # Create run document upfront so we can return the ID immediately
    now_start = datetime.now(timezone.utc).isoformat()
    run_doc = {
        "stage": body.stage.value,
        "persona": persona,
        "target": body.target_url,
        "goal": body.goal,
        "outcome": "in_progress",
        "started_at": now_start,
        "ended_at": None,
    }
    run_result = await db.runs.insert_one(run_doc)
    run_id = str(run_result.inserted_id)

    # Launch engine in background task
    task = _asyncio.create_task(
        _run_engine_background(run_id, body.target_url, body.goal, persona, body.stage.value)
    )
    _engine_tasks[run_id] = task

    return JSONResponse(
        status_code=202,
        content={
            "run_id": run_id,
            "status": "started",
            "message": "Engine run started in background. Poll GET /api/engine/run/{run_id} for results.",
        },
    )

@api_router.get("/engine/run/{run_id}")
async def get_engine_run_status(run_id: str):
    """Poll for engine run results."""
    try:
        oid = ObjectId(run_id)
    except Exception:
        raise HTTPException(400, "Invalid run ID")

    run_doc = await db.runs.find_one({"_id": oid})
    if not run_doc:
        raise HTTPException(404, "Run not found")

    run_data = {
        "run_id": run_id,
        "outcome": run_doc.get("outcome", "in_progress"),
        "stage": run_doc.get("stage"),
        "target": run_doc.get("target"),
        "goal": run_doc.get("goal"),
        "started_at": run_doc.get("started_at"),
        "ended_at": run_doc.get("ended_at"),
        "browserbase_session_id": run_doc.get("browserbase_session_id"),
        "persona": run_doc.get("persona"),
        "still_running": run_id in _engine_tasks,
        "paused": run_doc.get("paused", False),
        "error": run_doc.get("error"),
    }

    # Always include steps/signals so far — the live activity feed backfills from
    # this on open (whether the run is still in progress or already finished),
    # then subscribes to the WS for anything after.
    steps_cursor = db.steps.find({"run_id": run_id}).sort("index", 1)
    steps = await steps_cursor.to_list(50)
    signals_cursor = db.signals.find({"run_id": run_id}).sort("severity", -1)
    signals = await signals_cursor.to_list(50)

    run_data["steps"] = [
        {
            "index": s.get("index"),
            "action": s.get("action"),
            "reasoning": s.get("reasoning", "")[:300],
            "screenshot_before_url": s.get("screenshot_before_url"),
            "screenshot_after_url": s.get("screenshot_after_url"),
            "location": s.get("location"),
            "action_result": s.get("action_result"),
            "action_rejected": s.get("action_rejected", False),
            "frustration_at_step": s.get("frustration_at_step"),
            "timestamp": s.get("timestamp"),
        }
        for s in steps
    ]
    run_data["signals"] = [
        {
            "type": sig.get("type"),
            "severity": sig.get("severity"),
            "screen": sig.get("screen"),
            "description": sig.get("description"),
        }
        for sig in signals
    ]
    run_data["total_steps"] = len(steps)
    run_data["total_signals"] = len(signals)

    return run_data


@api_router.get("/engine/run/{run_id}/live")
async def get_engine_run_live_view(run_id: str):
    """
    Return an embeddable Browserbase live-view URL for a running session.

    status:
      - "pending" : run started but the Browserbase session isn't attached yet
      - "live"    : `live_url` is an iframe-able view of the running browser
      - "ended"   : run finished / session gone; `replay_url` links to the recording
    """
    try:
        oid = ObjectId(run_id)
    except Exception:
        raise HTTPException(400, "Invalid run ID")

    run_doc = await db.runs.find_one({"_id": oid})
    if not run_doc:
        raise HTTPException(404, "Run not found")

    session_id = run_doc.get("browserbase_session_id")
    outcome = run_doc.get("outcome", "in_progress")
    replay_url = f"https://www.browserbase.com/sessions/{session_id}" if session_id else None

    if not session_id:
        return {"status": "pending", "run_id": run_id}

    if outcome != "in_progress":
        return {"status": "ended", "run_id": run_id, "session_id": session_id, "replay_url": replay_url}

    # Session should be live — ask Browserbase for the live-view URLs.
    try:
        from browserbase import Browserbase
        bb = Browserbase(api_key=os.environ["BROWSERBASE_API_KEY"])
        live = await _asyncio.to_thread(bb.sessions.debug, session_id)
        return {
            "status": "live",
            "run_id": run_id,
            "session_id": session_id,
            "live_url": live.debugger_fullscreen_url,
            "replay_url": replay_url,
        }
    except Exception as e:
        logger.warning("Browserbase debug() failed for session %s: %s", session_id, e)
        # Session likely already ended between our DB read and this call.
        return {"status": "ended", "run_id": run_id, "session_id": session_id, "replay_url": replay_url}


@api_router.post("/engine/run/{run_id}/pause")
async def pause_engine_run(run_id: str):
    """Pause a running persona between steps. Takes effect after the in-flight step finishes."""
    import run_control
    try:
        oid = ObjectId(run_id)
    except Exception:
        raise HTTPException(400, "Invalid run ID")

    run_doc = await db.runs.find_one({"_id": oid})
    if not run_doc:
        raise HTTPException(404, "Run not found")
    if run_doc.get("outcome") != "in_progress":
        raise HTTPException(409, "Run has already finished")

    if not run_control.pause(run_id):
        raise HTTPException(409, "Run is not currently active")

    await db.runs.update_one({"_id": oid}, {"$set": {"paused": True}})
    await broadcaster.broadcast({"type": "run_paused", "run_id": run_id})
    return {"run_id": run_id, "paused": True}


@api_router.post("/engine/run/{run_id}/resume")
async def resume_engine_run(run_id: str):
    """Resume a paused persona run."""
    import run_control
    try:
        oid = ObjectId(run_id)
    except Exception:
        raise HTTPException(400, "Invalid run ID")

    run_doc = await db.runs.find_one({"_id": oid})
    if not run_doc:
        raise HTTPException(404, "Run not found")
    if run_doc.get("outcome") != "in_progress":
        raise HTTPException(409, "Run has already finished")

    if not run_control.resume(run_id):
        raise HTTPException(409, "Run is not currently active")

    await db.runs.update_one({"_id": oid}, {"$set": {"paused": False}})
    await broadcaster.broadcast({"type": "run_resumed", "run_id": run_id})
    return {"run_id": run_id, "paused": False}


@app.websocket("/api/ws/runs")
async def ws_runs(ws: WebSocket):
    """Live feed of step_update / run_complete / run_paused / run_resumed events."""
    await broadcaster.connect(ws)
    try:
        while True:
            # Client doesn't send anything meaningful — just keep the socket open
            # and notice disconnects.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await broadcaster.disconnect(ws)


# --- Parallel Panel Engine ---

class PanelRunRequest(BaseModel):
    target_url: str = "https://tier3.college"
    goal: str = "Find the pricing page"
    stage: StageEnum = StageEnum.prototype
    persona_panel_id: Optional[str] = None
    persona_indices: Optional[List[int]] = None  # specific indices, or None for first N
    concurrency: int = 3

# batch_id -> list of run_ids for tracking
_batch_tasks: dict = {}  # batch_id -> asyncio.Task

async def _run_panel_background(batch_id: str, target_url: str, goal: str, personas: list, stage: str, concurrency: int):
    """Background wrapper for parallel panel runs."""
    from engine import run_panel_parallel
    try:
        result = await run_panel_parallel(
            db=db,
            target_url=target_url,
            goal=goal,
            personas=personas,
            stage=stage,
            concurrency=concurrency,
            batch_id=batch_id,
        )
        return result
    except Exception as e:
        logger.exception("Panel run batch %s failed: %s", batch_id, e)
        return {"batch_id": batch_id, "error": str(e)}
    finally:
        _batch_tasks.pop(batch_id, None)

@api_router.post("/engine/run-panel")
async def engine_run_panel(body: PanelRunRequest):
    """Start parallel engine runs for multiple personas from a panel."""
    import uuid as _uuid
    from paywall import consume_credit

    # Paywall check
    if not await consume_credit(db):
        raise HTTPException(402, "Payment required. Purchase a run credit first.")

    # Resolve panel
    if body.persona_panel_id:
        try:
            panel_doc = await db.persona_panels.find_one({"_id": ObjectId(body.persona_panel_id)})
        except Exception:
            raise HTTPException(400, "Invalid persona_panel_id")
        if not panel_doc:
            raise HTTPException(404, "Persona panel not found")
    else:
        panel_doc = await db.persona_panels.find_one({"client_ref": "seed-demo"})
        if not panel_doc:
            raise HTTPException(400, "No panel found")

    all_personas = panel_doc.get("personas", [])
    if not all_personas:
        raise HTTPException(400, "Panel has no personas")

    # Select personas
    if body.persona_indices:
        selected = []
        for idx in body.persona_indices:
            if idx < 0 or idx >= len(all_personas):
                raise HTTPException(400, f"persona_indices contains out-of-range index {idx} (panel has {len(all_personas)} personas)")
            selected.append(all_personas[idx])
    else:
        selected = all_personas[:body.concurrency]

    batch_id = str(_uuid.uuid4())

    # Launch in background
    task = _asyncio.create_task(
        _run_panel_background(batch_id, body.target_url, body.goal, selected, body.stage.value, body.concurrency)
    )
    _batch_tasks[batch_id] = task

    return JSONResponse(
        status_code=202,
        content={
            "batch_id": batch_id,
            "status": "started",
            "persona_count": len(selected),
            "personas": [p.get("name", "?") for p in selected],
            "message": f"Panel run started with {len(selected)} personas. Poll GET /api/engine/batch/{'{batch_id}'} for results.",
        },
    )

@api_router.get("/engine/batch/{batch_id}")
async def get_engine_batch_status(batch_id: str):
    """Poll for parallel panel run results."""
    still_running = batch_id in _batch_tasks

    # Find all runs in this batch
    cursor = db.runs.find({"batch_id": batch_id}).sort("started_at", 1)
    runs = await cursor.to_list(20)

    if not runs:
        raise HTTPException(404, "Batch not found")

    run_summaries = []
    for r in runs:
        rid = str(r["_id"])
        summary = {
            "run_id": rid,
            "persona_name": r.get("persona", {}).get("name", "?"),
            "outcome": r.get("outcome", "in_progress"),
            "started_at": r.get("started_at"),
            "ended_at": r.get("ended_at"),
            "browserbase_session_id": r.get("browserbase_session_id"),
        }
        # If completed, count steps and signals
        if r.get("outcome") != "in_progress":
            step_count = await db.steps.count_documents({"run_id": rid})
            signal_count = await db.signals.count_documents({"run_id": rid})
            # Count rejected actions specifically
            rejected_count = await db.signals.count_documents({
                "run_id": rid,
                "type": "behavioral",
                "description": {"$regex": "rejected"},
            })
            summary["total_steps"] = step_count
            summary["total_signals"] = signal_count
            summary["rejected_actions"] = rejected_count
        run_summaries.append(summary)

    all_done = all(r["outcome"] != "in_progress" for r in run_summaries)

    return {
        "batch_id": batch_id,
        "still_running": still_running,
        "all_done": all_done,
        "total_runs": len(run_summaries),
        "runs": run_summaries,
    }


# --- Persona Generator ---

class GeneratePersonasRequest(BaseModel):
    audience_description: str
    count: int = Field(default=4, ge=3, le=5)

@api_router.post("/generate-personas")
async def generate_personas_endpoint(body: GeneratePersonasRequest):
    from generator import generate_personas
    try:
        result = await generate_personas(
            audience_description=body.audience_description,
            count=body.count,
        )
        return result
    except Exception as e:
        logger.exception("Persona generation failed")
        raise HTTPException(500, detail=str(e))


# --- Prototype: Screen Graphs + Engine ---

class ScreenNode(BaseModel):
    id: str
    name: str
    image_url: str = ""

class TransitionEdge(BaseModel):
    from_screen: str
    label: str
    to_screen: str

class ScreenGraphCreate(BaseModel):
    name: str
    screens: List[ScreenNode] = []
    transitions: List[TransitionEdge] = []
    start_screen: str = ""

class ScreenGraphUpdate(BaseModel):
    name: Optional[str] = None
    screens: Optional[List[ScreenNode]] = None
    transitions: Optional[List[TransitionEdge]] = None
    start_screen: Optional[str] = None

class PrototypeRunRequest(BaseModel):
    graph_id: str
    goal: str = "Find the pricing page"
    persona_panel_id: Optional[str] = None
    persona_indices: Optional[List[int]] = None
    concurrency: int = 3

@api_router.post("/prototype/graphs")
async def create_screen_graph(body: ScreenGraphCreate):
    doc = {
        "name": body.name,
        "screens": [s.model_dump() for s in body.screens],
        "transitions": [t.model_dump() for t in body.transitions],
        "start_screen": body.start_screen,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.screen_graphs.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    return {k: v for k, v in doc.items() if k != "_id"}

@api_router.get("/prototype/graphs")
async def list_screen_graphs():
    cursor = db.screen_graphs.find().sort("created_at", -1)
    docs = await cursor.to_list(50)
    return [
        {**{k: v for k, v in d.items() if k != "_id"}, "id": str(d["_id"])}
        for d in docs
    ]

@api_router.get("/prototype/graphs/{graph_id}")
async def get_screen_graph(graph_id: str):
    try:
        oid = ObjectId(graph_id)
    except Exception:
        raise HTTPException(400, "Invalid graph ID")
    doc = await db.screen_graphs.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Screen graph not found")
    return {**{k: v for k, v in doc.items() if k != "_id"}, "id": str(doc["_id"])}

@api_router.patch("/prototype/graphs/{graph_id}")
async def update_screen_graph(graph_id: str, body: ScreenGraphUpdate):
    try:
        oid = ObjectId(graph_id)
    except Exception:
        raise HTTPException(400, "Invalid graph ID")
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.screens is not None:
        updates["screens"] = [s.model_dump() for s in body.screens]
    if body.transitions is not None:
        updates["transitions"] = [t.model_dump() for t in body.transitions]
    if body.start_screen is not None:
        updates["start_screen"] = body.start_screen
    if not updates:
        raise HTTPException(400, "No fields to update")
    await db.screen_graphs.update_one({"_id": oid}, {"$set": updates})
    doc = await db.screen_graphs.find_one({"_id": oid})
    return {**{k: v for k, v in doc.items() if k != "_id"}, "id": str(doc["_id"])}

@api_router.delete("/prototype/graphs/{graph_id}")
async def delete_screen_graph(graph_id: str):
    try:
        oid = ObjectId(graph_id)
    except Exception:
        raise HTTPException(400, "Invalid graph ID")
    result = await db.screen_graphs.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(404, "Screen graph not found")
    return {"deleted": True}

@api_router.post("/prototype/upload-mockup")
async def upload_mockup(file: UploadFile = FastAPIFile(...)):
    """Upload a mockup image to Cloudinary, return the URL."""
    import cloudinary
    import cloudinary.uploader
    import io

    cloudinary.config(
        cloud_name=os.environ.get("CLOUDINARY_CLOUD_NAME"),
        api_key=os.environ.get("CLOUDINARY_API_KEY"),
        api_secret=os.environ.get("CLOUDINARY_API_SECRET"),
        secure=True,
    )
    contents = await file.read()
    try:
        result = cloudinary.uploader.upload(
            io.BytesIO(contents),
            folder="synthtest/mockups",
            resource_type="image",
        )
        return {"url": result["secure_url"], "public_id": result["public_id"]}
    except Exception as e:
        raise HTTPException(502, detail=f"Cloudinary upload failed: {e}")

# Background tasks for prototype runs
_proto_batch_tasks: dict = {}

async def _run_proto_background(batch_id, graph_id, goal, personas, concurrency):
    from prototype_engine import run_prototype_panel
    try:
        return await run_prototype_panel(
            db=db, graph_id=graph_id, goal=goal,
            personas=personas, concurrency=concurrency, batch_id=batch_id,
        )
    except Exception as e:
        logger.exception("Prototype batch %s failed", batch_id)
        return {"batch_id": batch_id, "error": str(e)}
    finally:
        _proto_batch_tasks.pop(batch_id, None)

@api_router.post("/prototype/run")
async def prototype_run(body: PrototypeRunRequest):
    """Start prototype persona runs against a screen graph."""
    import uuid as _uuid
    from paywall import consume_credit

    # Paywall check
    if not await consume_credit(db):
        raise HTTPException(402, "Payment required. Purchase a run credit first.")

    # Verify graph exists
    try:
        graph_doc = await db.screen_graphs.find_one({"_id": ObjectId(body.graph_id)})
    except Exception:
        raise HTTPException(400, "Invalid graph_id")
    if not graph_doc:
        raise HTTPException(404, "Screen graph not found")

    # Resolve personas
    if body.persona_panel_id:
        try:
            panel = await db.persona_panels.find_one({"_id": ObjectId(body.persona_panel_id)})
        except Exception:
            raise HTTPException(400, "Invalid persona_panel_id")
        if not panel:
            raise HTTPException(404, "Persona panel not found")
        all_personas = panel.get("personas", [])
    else:
        seed = await db.persona_panels.find_one({"client_ref": "seed-demo"})
        if not seed:
            raise HTTPException(400, "No panel found")
        all_personas = seed.get("personas", [])

    if body.persona_indices:
        selected = [all_personas[i] for i in body.persona_indices if i < len(all_personas)]
    else:
        selected = all_personas[:body.concurrency]

    if not selected:
        raise HTTPException(400, "No personas selected")

    batch_id = str(_uuid.uuid4())
    task = _asyncio.create_task(
        _run_proto_background(batch_id, body.graph_id, body.goal, selected, body.concurrency)
    )
    _proto_batch_tasks[batch_id] = task

    return JSONResponse(status_code=202, content={
        "batch_id": batch_id,
        "status": "started",
        "stage": "prototype",
        "persona_count": len(selected),
        "personas": [p.get("name", "?") for p in selected],
    })


# --- Signal Aggregation ---

@api_router.get("/diff")
async def cross_stage_diff(
    goal: Optional[str] = None,
    prototype_batch_id: Optional[str] = None,
    runtime_batch_id: Optional[str] = None,
    prototype_run_ids: Optional[str] = None,
    runtime_run_ids: Optional[str] = None,
):
    """
    Compare prototype vs runtime signals for the same goal/personas.
    Returns a regression report grouped by screen.
    """
    from diff import build_cross_stage_diff

    proto_ids = [r.strip() for r in prototype_run_ids.split(",") if r.strip()] if prototype_run_ids else None
    rt_ids = [r.strip() for r in runtime_run_ids.split(",") if r.strip()] if runtime_run_ids else None

    if not goal and not prototype_batch_id and not runtime_batch_id and not proto_ids and not rt_ids:
        raise HTTPException(400, "Provide goal, batch IDs, or run IDs")

    result = await build_cross_stage_diff(
        db,
        goal=goal,
        prototype_batch_id=prototype_batch_id,
        runtime_batch_id=runtime_batch_id,
        prototype_run_ids=proto_ids,
        runtime_run_ids=rt_ids,
    )
    if "error" in result:
        raise HTTPException(400, result["error"])
    return result

@api_router.get("/signals/aggregate")
async def aggregate_signals(
    batch_id: Optional[str] = None,
    run_ids: Optional[str] = None,
):
    """
    Aggregate signals by screen, weighted by frequency × severity.
    Returns ranked list of worst screens.
    Provide either batch_id or comma-separated run_ids.
    """
    from signals import aggregate_signals_by_screen

    rid_list = None
    if run_ids:
        rid_list = [r.strip() for r in run_ids.split(",") if r.strip()]

    if not batch_id and not rid_list:
        raise HTTPException(400, "Provide batch_id or run_ids parameter")

    result = await aggregate_signals_by_screen(db, batch_id=batch_id, run_ids=rid_list)
    return {
        "batch_id": batch_id,
        "total_screens": len(result),
        "screens": result,
    }


@api_router.get("/reports/run/{run_id}")
async def get_run_report(run_id: str, refresh: bool = False):
    """Developer-facing narrative report for a single run (LLM-generated, cached on the run)."""
    from reporter import generate_run_report
    try:
        ObjectId(run_id)
    except Exception:
        raise HTTPException(400, "Invalid run ID")
    try:
        return await generate_run_report(db, run_id, refresh=refresh)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception("Run report generation failed for %s", run_id)
        raise HTTPException(502, f"Report generation failed: {e}")


@api_router.get("/reports/batch/{batch_id}")
async def get_batch_report(batch_id: str, refresh: bool = False):
    """Developer-facing narrative report synthesized across all runs in a batch."""
    from reporter import generate_batch_report
    try:
        return await generate_batch_report(db, batch_id, refresh=refresh)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        logger.exception("Batch report generation failed for %s", batch_id)
        raise HTTPException(502, f"Report generation failed: {e}")


@api_router.post("/signals/derive/{run_id}")
async def derive_signals_for_run(run_id: str):
    """Manually trigger signal derivation for an existing run."""
    from signals import derive_all_signals
    try:
        oid = ObjectId(run_id)
    except Exception:
        raise HTTPException(400, "Invalid run ID")

    run_doc = await db.runs.find_one({"_id": oid})
    if not run_doc:
        raise HTTPException(404, "Run not found")

    persona = run_doc.get("persona", {})
    stage = run_doc.get("stage", "prototype")

    derived = await derive_all_signals(db, run_id, stage, persona)
    return {
        "run_id": run_id,
        "derived_count": len(derived),
        "signals": derived,
    }


# --- Runs CRUD ---

@api_router.post("/runs", response_model=dict)
async def create_run(body: RunCreate):
    run = Run(
        stage=body.stage,
        persona=body.persona,
        target=body.target,
        goal=body.goal,
        outcome=body.outcome,
        started_at=datetime.now(timezone.utc).isoformat(),
    )
    doc = run.to_mongo()
    result = await db.runs.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return Run.from_mongo(doc).model_dump(by_alias=False)

@api_router.get("/runs", response_model=list)
async def list_runs(
    stage: Optional[StageEnum] = None,
    outcome: Optional[OutcomeEnum] = None,
    limit: int = Query(default=100, le=500),
    skip: int = Query(default=0, ge=0),
):
    query = {}
    if stage:
        query["stage"] = stage.value
    if outcome:
        query["outcome"] = outcome.value
    cursor = db.runs.find(query).sort("started_at", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(limit)
    return [Run.from_mongo(d).model_dump(by_alias=False) for d in docs]

@api_router.get("/runs/{run_id}", response_model=dict)
async def get_run(run_id: str):
    try:
        oid = ObjectId(run_id)
    except (InvalidId, Exception):
        raise HTTPException(400, "Invalid run ID")
    doc = await db.runs.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Run not found")
    return Run.from_mongo(doc).model_dump(by_alias=False)

@api_router.patch("/runs/{run_id}", response_model=dict)
async def update_run(run_id: str, body: RunUpdate):
    try:
        oid = ObjectId(run_id)
    except (InvalidId, Exception):
        raise HTTPException(400, "Invalid run ID")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    await db.runs.update_one({"_id": oid}, {"$set": updates})
    doc = await db.runs.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Run not found")
    return Run.from_mongo(doc).model_dump(by_alias=False)

@api_router.delete("/runs/{run_id}")
async def delete_run(run_id: str):
    try:
        oid = ObjectId(run_id)
    except (InvalidId, Exception):
        raise HTTPException(400, "Invalid run ID")
    result = await db.runs.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(404, "Run not found")
    await db.steps.delete_many({"run_id": run_id})
    await db.signals.delete_many({"run_id": run_id})
    return {"deleted": True}


# --- Steps CRUD ---

@api_router.post("/steps", response_model=dict)
async def create_step(body: StepCreate):
    step = Step(
        run_id=body.run_id,
        index=body.index,
        action=body.action,
        reasoning=body.reasoning,
        screenshot_before_url=body.screenshot_before_url,
        screenshot_after_url=body.screenshot_after_url,
        location=body.location,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
    doc = step.to_mongo()
    result = await db.steps.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return Step.from_mongo(doc).model_dump(by_alias=False)

@api_router.get("/steps", response_model=list)
async def list_steps(
    run_id: Optional[str] = None,
    limit: int = Query(default=200, le=1000),
    skip: int = Query(default=0, ge=0),
):
    query = {}
    if run_id:
        query["run_id"] = run_id
    cursor = db.steps.find(query).sort("index", 1).skip(skip).limit(limit)
    docs = await cursor.to_list(limit)
    return [Step.from_mongo(d).model_dump(by_alias=False) for d in docs]

@api_router.get("/steps/{step_id}", response_model=dict)
async def get_step(step_id: str):
    try:
        oid = ObjectId(step_id)
    except (InvalidId, Exception):
        raise HTTPException(400, "Invalid step ID")
    doc = await db.steps.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Step not found")
    return Step.from_mongo(doc).model_dump(by_alias=False)

@api_router.delete("/steps/{step_id}")
async def delete_step(step_id: str):
    try:
        oid = ObjectId(step_id)
    except (InvalidId, Exception):
        raise HTTPException(400, "Invalid step ID")
    result = await db.steps.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(404, "Step not found")
    return {"deleted": True}


# --- Signals CRUD ---

@api_router.post("/signals", response_model=dict)
async def create_signal(body: SignalCreate):
    signal = Signal(
        run_id=body.run_id,
        stage=body.stage,
        type=body.type,
        severity=body.severity,
        screen=body.screen,
        description=body.description,
    )
    doc = signal.to_mongo()
    result = await db.signals.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return Signal.from_mongo(doc).model_dump(by_alias=False)

@api_router.get("/signals", response_model=list)
async def list_signals(
    run_id: Optional[str] = None,
    stage: Optional[StageEnum] = None,
    type: Optional[SignalTypeEnum] = None,
    severity_min: Optional[int] = None,
    limit: int = Query(default=200, le=1000),
    skip: int = Query(default=0, ge=0),
):
    query = {}
    if run_id:
        query["run_id"] = run_id
    if stage:
        query["stage"] = stage.value
    if type:
        query["type"] = type.value
    if severity_min is not None:
        query["severity"] = {"$gte": severity_min}
    cursor = db.signals.find(query).sort("severity", -1).skip(skip).limit(limit)
    docs = await cursor.to_list(limit)
    return [Signal.from_mongo(d).model_dump(by_alias=False) for d in docs]

@api_router.get("/signals/{signal_id}", response_model=dict)
async def get_signal(signal_id: str):
    try:
        oid = ObjectId(signal_id)
    except (InvalidId, Exception):
        raise HTTPException(400, "Invalid signal ID")
    doc = await db.signals.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Signal not found")
    return Signal.from_mongo(doc).model_dump(by_alias=False)

@api_router.delete("/signals/{signal_id}")
async def delete_signal(signal_id: str):
    try:
        oid = ObjectId(signal_id)
    except (InvalidId, Exception):
        raise HTTPException(400, "Invalid signal ID")
    result = await db.signals.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(404, "Signal not found")
    return {"deleted": True}


# --- Persona Panels CRUD ---

@api_router.post("/persona-panels", response_model=dict)
async def create_persona_panel(body: PersonaPanelCreate):
    panel = PersonaPanel(
        client_ref=body.client_ref,
        audience_description=body.audience_description,
        personas=body.personas,
        composition=body.composition,
    )
    doc = panel.to_mongo()
    result = await db.persona_panels.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return PersonaPanel.from_mongo(doc).model_dump(by_alias=False)

@api_router.get("/persona-panels", response_model=list)
async def list_persona_panels(
    limit: int = Query(default=100, le=500),
    skip: int = Query(default=0, ge=0),
):
    cursor = db.persona_panels.find().skip(skip).limit(limit)
    docs = await cursor.to_list(limit)
    return [PersonaPanel.from_mongo(d).model_dump(by_alias=False) for d in docs]

@api_router.get("/persona-panels/{panel_id}", response_model=dict)
async def get_persona_panel(panel_id: str):
    try:
        oid = ObjectId(panel_id)
    except (InvalidId, Exception):
        raise HTTPException(400, "Invalid panel ID")
    doc = await db.persona_panels.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Persona panel not found")
    return PersonaPanel.from_mongo(doc).model_dump(by_alias=False)

@api_router.patch("/persona-panels/{panel_id}", response_model=dict)
async def update_persona_panel(panel_id: str, body: PersonaPanelUpdate):
    try:
        oid = ObjectId(panel_id)
    except (InvalidId, Exception):
        raise HTTPException(400, "Invalid panel ID")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    if "composition" in updates:
        updates["composition"] = updates["composition"].value if isinstance(updates["composition"], CompositionEnum) else updates["composition"]
    await db.persona_panels.update_one({"_id": oid}, {"$set": updates})
    doc = await db.persona_panels.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Persona panel not found")
    return PersonaPanel.from_mongo(doc).model_dump(by_alias=False)

@api_router.delete("/persona-panels/{panel_id}")
async def delete_persona_panel(panel_id: str):
    try:
        oid = ObjectId(panel_id)
    except (InvalidId, Exception):
        raise HTTPException(400, "Invalid panel ID")
    result = await db.persona_panels.delete_one({"_id": oid})
    if result.deleted_count == 0:
        raise HTTPException(404, "Persona panel not found")
    return {"deleted": True}


# --- Seed Data ---

SEED_PANEL = {
    "client_ref": "seed-demo",
    "audience_description": "Seed panel for skeleton testing — covers baseline + all disability constraint types",
    "composition": "broad",
    "personas": [
        {
            "name": "Priya — Rushed Professional",
            "traits": "28, urban, tech-savvy, multitasking, low patience for friction",
            "disability": None,
            "accent_color": "#818CF8",
            "allowed_actions": ["click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"],
            "perception_mode": "full",
            "viewport_zoom": 1.0,
            "frustration_budget": 3,
            "tolerance_rules": [
                "abandon if the task takes noticeably more steps than expected",
                "flag any page that feels slow to respond"
            ],
            "temperature": 0.6
        },
        {
            "name": "Arun — Keyboard Only",
            "traits": "motor impairment, navigates entirely by keyboard, no mouse",
            "disability": "motor",
            "accent_color": "#A78BFA",
            "allowed_actions": ["type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"],
            "perception_mode": "full",
            "viewport_zoom": 1.0,
            "frustration_budget": 4,
            "tolerance_rules": [
                "flag any control not reachable by keyboard alone",
                "flag any focus trap or unclear focus order"
            ],
            "temperature": 0.6
        },
        {
            "name": "Meera — Screen Reader User",
            "traits": "blind, navigates via screen reader, no visual reference",
            "disability": "blind",
            "accent_color": "#38BDF8",
            "allowed_actions": ["click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"],
            "perception_mode": "ax_tree_only",
            "viewport_zoom": 1.0,
            "frustration_budget": 4,
            "tolerance_rules": [
                "flag any unlabeled button, image, or form field",
                "flag reading order that doesn't match logical task order"
            ],
            "temperature": 0.6
        },
        {
            "name": "Devika — Low Vision",
            "traits": "low vision, relies on significant zoom, some mouse use",
            "disability": "low_vision",
            "accent_color": "#C084FC",
            "allowed_actions": ["click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"],
            "perception_mode": "zoomed",
            "viewport_zoom": 2.0,
            "frustration_budget": 5,
            "tolerance_rules": [
                "flag text or controls that overlap, clip, or vanish when zoomed",
                "flag any meaning conveyed by color alone"
            ],
            "temperature": 0.6
        },
        {
            "name": "Farhan — First-Time, Low Literacy",
            "traits": "low English literacy, unfamiliar with the product category, easily overwhelmed",
            "disability": "cognitive",
            "accent_color": "#F472B6",
            "allowed_actions": ["click", "type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"],
            "perception_mode": "full",
            "viewport_zoom": 1.0,
            "frustration_budget": 2,
            "tolerance_rules": [
                "flag dense paragraphs or unexplained jargon",
                "flag multi-step forms with no visible progress",
                "flag any action that feels time-pressured"
            ],
            "temperature": 0.7
        }
    ]
}

@api_router.post("/seed")
async def seed_data():
    existing = await db.persona_panels.find_one({"client_ref": "seed-demo"})
    if existing:
        # Update personas to latest spec
        await db.persona_panels.update_one(
            {"_id": existing["_id"]},
            {"$set": {"personas": SEED_PANEL["personas"]}},
        )
        return {"message": "Seed data updated", "panel_id": str(existing["_id"])}
    result = await db.persona_panels.insert_one(SEED_PANEL.copy())
    return {"message": "Seed data created", "panel_id": str(result.inserted_id)}


# --- Startup ---

@app.on_event("startup")
async def startup():
    logger.info("Starting up — seeding data if needed")

    # Reconcile orphaned runs: any run left "in_progress" from a previous process
    # (hard restart, crash, hot-reload) has no live task and will never finalize.
    # Mark them gave_up so the UI/reports don't show a permanent "Running".
    orphaned = await db.runs.update_many(
        {"outcome": "in_progress"},
        {"$set": {"outcome": "gave_up", "ended_at": datetime.now(timezone.utc).isoformat(),
                  "error": "Orphaned on backend restart — engine task no longer running"}},
    )
    if orphaned.modified_count:
        logger.warning("Reconciled %d orphaned in_progress run(s) -> gave_up", orphaned.modified_count)

    existing = await db.persona_panels.find_one({"client_ref": "seed-demo"})
    if not existing:
        await db.persona_panels.insert_one(SEED_PANEL.copy())
        logger.info("Seed persona panel created")
    else:
        # Always update personas to latest spec
        await db.persona_panels.update_one(
            {"_id": existing["_id"]},
            {"$set": {"personas": SEED_PANEL["personas"]}},
        )
        logger.info("Seed persona panel updated to latest spec")


# --- Include Router & Middleware ---

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("shutdown")
async def shutdown_db_client():
    # Cancel in-flight engine tasks and mark runs as gave_up
    for run_id, task in list(_engine_tasks.items()):
        task.cancel()
        try:
            await db.runs.update_one(
                {"_id": ObjectId(run_id), "outcome": "in_progress"},
                {"$set": {"outcome": "gave_up", "ended_at": datetime.now(timezone.utc).isoformat()}},
            )
            logger.info("Marked orphaned run %s as gave_up on shutdown", run_id)
        except Exception:
            pass
    _engine_tasks.clear()
    # Cancel in-flight batch tasks
    for batch_id, task in list(_batch_tasks.items()):
        task.cancel()
    _batch_tasks.clear()
    for batch_id, task in list(_proto_batch_tasks.items()):
        task.cancel()
    _proto_batch_tasks.clear()
    client.close()
