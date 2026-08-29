from fastapi import FastAPI, APIRouter, HTTPException, Query
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

class SignalCreate(BaseModel):
    run_id: str
    stage: StageEnum
    type: SignalTypeEnum
    severity: int = Field(ge=1, le=5)
    screen: str = ""
    description: str = ""


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

async def _run_engine_background(run_id: str, target_url: str, goal: str, persona: dict, stage: str):
    """Background wrapper that catches all errors and finalizes the run."""
    from engine import run_persona_engine
    try:
        result = await run_persona_engine(
            db=db,
            target_url=target_url,
            goal=goal,
            persona=persona,
            stage=stage,
            existing_run_id=run_id,
        )
        return result
    except Exception as e:
        logger.exception("Background engine run failed for %s", run_id)
        # Try to update the run as gave_up
        try:
            from bson import ObjectId as OID
            await db.runs.update_one(
                {"_id": OID(run_id)},
                {"$set": {"outcome": "gave_up", "ended_at": datetime.now(timezone.utc).isoformat()}}
            )
        except Exception:
            pass
        return {"run_id": run_id, "outcome": "gave_up", "error": str(e)}
    finally:
        _engine_tasks.pop(run_id, None)

from starlette.responses import JSONResponse

@api_router.post("/engine/run")
async def engine_run(body: EngineRunRequest):
    from engine import run_persona_engine
    from browser import BrowserUpstreamError, BrowserTimeoutError

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
    }

    # If completed, include steps and signals
    if run_doc.get("outcome") != "in_progress" or run_id not in _engine_tasks:
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
            "allowed_actions": ["type", "scroll", "navigate", "wait", "key", "report_friction", "give_up"],
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
        return {"message": "Seed data already exists", "panel_id": str(existing["_id"])}
    result = await db.persona_panels.insert_one(SEED_PANEL.copy())
    return {"message": "Seed data created", "panel_id": str(result.inserted_id)}


# --- Startup ---

@app.on_event("startup")
async def startup():
    logger.info("Starting up — seeding data if needed")
    existing = await db.persona_panels.find_one({"client_ref": "seed-demo"})
    if not existing:
        await db.persona_panels.insert_one(SEED_PANEL.copy())
        logger.info("Seed persona panel created")
    else:
        logger.info("Seed persona panel already exists")


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
    client.close()
