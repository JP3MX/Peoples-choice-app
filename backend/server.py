from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import io
import re
import uuid
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import bcrypt
import jwt
import requests
from bson import ObjectId
from pypdf import PdfReader
from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File, Form, Header, Query
from fastapi.responses import StreamingResponse, Response
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field

from emergentintegrations.llm.chat import LlmChat, UserMessage, TextDelta, StreamDone
from corpus_seed import HISTORICAL_RECORDS, STARTER_AIRCRAFT

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("squawkking")

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_ALGORITHM = "HS256"
EMERGENT_KEY = os.environ.get("EMERGENT_LLM_KEY")
APP_NAME = "squawkking"
STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"

STOP_MESSAGE = "Approved maintenance data required. Please provide or upload the applicable manual before continuing."

app = FastAPI(title="Squawk King IA")
api_router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# Object storage helpers
# ---------------------------------------------------------------------------
storage_key = None

def init_storage(force: bool = False):
    global storage_key
    if storage_key and not force:
        return storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": EMERGENT_KEY}, timeout=30)
    resp.raise_for_status()
    storage_key = resp.json()["storage_key"]
    return storage_key

def put_object(path: str, data: bytes, content_type: str) -> dict:
    key = init_storage()
    resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                        headers={"X-Storage-Key": key, "Content-Type": content_type},
                        data=data, timeout=120)
    if resp.status_code == 404:
        key = init_storage(force=True)
        resp = requests.put(f"{STORAGE_URL}/objects/{path}",
                            headers={"X-Storage-Key": key, "Content-Type": content_type},
                            data=data, timeout=120)
    resp.raise_for_status()
    return resp.json()

def get_object(path: str):
    key = init_storage()
    resp = requests.get(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    resp.raise_for_status()
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def create_access_token(user_id: str, email: str) -> str:
    payload = {"sub": user_id, "email": email,
               "exp": datetime.now(timezone.utc) + timedelta(days=7), "type": "access"}
    return jwt.encode(payload, os.environ["JWT_SECRET"], algorithm=JWT_ALGORITHM)

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
        user = await db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        user["id"] = str(user["_id"])
        user.pop("_id", None)
        user.pop("password_hash", None)
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = "Mechanic"

class LoginInput(BaseModel):
    email: EmailStr
    password: str

class AircraftInput(BaseModel):
    tail_number: str = ""
    make: str = ""
    model: str = ""
    year: str = ""
    serial_number: str = ""
    configuration: str = ""
    confirmed: bool = False

class LogbookInput(BaseModel):
    aircraft_id: Optional[str] = None
    date: str
    ata: str = ""
    description: str
    action_taken: str = ""
    hours: str = ""
    mechanic: str = ""

class SessionInput(BaseModel):
    title: Optional[str] = "New Troubleshooting Session"
    aircraft_id: Optional[str] = None

class MessageInput(BaseModel):
    text: str

# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@api_router.post("/auth/register")
async def register(payload: RegisterInput):
    email = payload.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = {"email": email, "password_hash": hash_password(payload.password),
           "name": payload.name or "Mechanic", "role": "mechanic",
           "created_at": datetime.now(timezone.utc).isoformat()}
    res = await db.users.insert_one(doc)
    uid = str(res.inserted_id)
    token = create_access_token(uid, email)
    return {"token": token, "user": {"id": uid, "email": email, "name": doc["name"], "role": "mechanic"}}

@api_router.post("/auth/login")
async def login(payload: LoginInput):
    email = payload.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    uid = str(user["_id"])
    token = create_access_token(uid, email)
    return {"token": token, "user": {"id": uid, "email": email, "name": user.get("name", "Mechanic"), "role": user.get("role", "mechanic")}}

@api_router.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user

# ---------------------------------------------------------------------------
# Aircraft routes
# ---------------------------------------------------------------------------
def clean(doc):
    doc.pop("_id", None)
    return doc

@api_router.get("/aircraft")
async def list_aircraft(user: dict = Depends(get_current_user)):
    items = await db.aircraft.find({"user_id": user["id"]}, {"_id": 0}).to_list(500)
    return items

@api_router.post("/aircraft")
async def create_aircraft(payload: AircraftInput, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc.update({"id": str(uuid.uuid4()), "user_id": user["id"],
                "created_at": datetime.now(timezone.utc).isoformat()})
    await db.aircraft.insert_one(dict(doc))
    return clean(doc)

@api_router.put("/aircraft/{aircraft_id}")
async def update_aircraft(aircraft_id: str, payload: AircraftInput, user: dict = Depends(get_current_user)):
    updates = payload.model_dump()
    res = await db.aircraft.update_one({"id": aircraft_id, "user_id": user["id"]}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Aircraft not found")
    doc = await db.aircraft.find_one({"id": aircraft_id}, {"_id": 0})
    return doc

@api_router.delete("/aircraft/{aircraft_id}")
async def delete_aircraft(aircraft_id: str, user: dict = Depends(get_current_user)):
    await db.aircraft.delete_one({"id": aircraft_id, "user_id": user["id"]})
    return {"ok": True}

# ---------------------------------------------------------------------------
# Manuals (PDF upload + extraction)
# ---------------------------------------------------------------------------
@api_router.get("/manuals")
async def list_manuals(aircraft_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {"user_id": user["id"], "is_deleted": False}
    if aircraft_id:
        q["aircraft_id"] = aircraft_id
    items = await db.manuals.find(q, {"_id": 0, "pages": 0}).to_list(500)
    return items

@api_router.post("/manuals")
async def upload_manual(
    file: UploadFile = File(...),
    aircraft_id: str = Form(""),
    doc_name: str = Form(""),
    doc_type: str = Form("AMM"),
    ata: str = Form(""),
    status: str = Form("current"),
    user: dict = Depends(get_current_user),
):
    data = await file.read()
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "pdf"
    path = f"{APP_NAME}/manuals/{user['id']}/{uuid.uuid4()}.{ext}"
    try:
        put_object(path, data, file.content_type or "application/pdf")
    except Exception as e:
        logger.error(f"storage upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage upload failed")

    pages = []
    full_text = ""
    if ext == "pdf":
        try:
            reader = PdfReader(io.BytesIO(data))
            for i, page in enumerate(reader.pages):
                txt = (page.extract_text() or "").strip()
                if txt:
                    pages.append({"page": i + 1, "text": txt})
                    full_text += "\n" + txt
        except Exception as e:
            logger.warning(f"pdf extract failed: {e}")

    doc = {
        "id": str(uuid.uuid4()), "user_id": user["id"], "aircraft_id": aircraft_id or None,
        "storage_path": path, "original_filename": file.filename,
        "doc_name": doc_name or file.filename, "doc_type": doc_type, "ata": ata,
        "status": status, "content_type": file.content_type or "application/pdf",
        "size": len(data), "page_count": len(pages), "pages": pages,
        "extracted_chars": len(full_text), "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.manuals.insert_one(dict(doc))
    doc.pop("pages", None)
    return clean(doc)

@api_router.put("/manuals/{manual_id}")
async def update_manual(manual_id: str, doc_name: str = Form(None), doc_type: str = Form(None),
                        ata: str = Form(None), status: str = Form(None),
                        aircraft_id: str = Form(None), user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in {"doc_name": doc_name, "doc_type": doc_type, "ata": ata,
                                 "status": status, "aircraft_id": aircraft_id}.items() if v is not None}
    if updates:
        await db.manuals.update_one({"id": manual_id, "user_id": user["id"]}, {"$set": updates})
    return {"ok": True}

@api_router.delete("/manuals/{manual_id}")
async def delete_manual(manual_id: str, user: dict = Depends(get_current_user)):
    await db.manuals.update_one({"id": manual_id, "user_id": user["id"]}, {"$set": {"is_deleted": True}})
    return {"ok": True}

@api_router.get("/manuals/{manual_id}/download")
async def download_manual(manual_id: str, authorization: str = Header(None), auth: str = Query(None)):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif auth:
        token = auth
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, os.environ["JWT_SECRET"], algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    record = await db.manuals.find_one({"id": manual_id, "user_id": payload["sub"], "is_deleted": False})
    if not record:
        raise HTTPException(status_code=404, detail="Manual not found")
    data, content_type = get_object(record["storage_path"])
    return Response(content=data, media_type=record.get("content_type", content_type),
                    headers={"Content-Disposition": f'inline; filename="{record["original_filename"]}"'})

# ---------------------------------------------------------------------------
# Historical corpus
# ---------------------------------------------------------------------------
@api_router.get("/corpus")
async def list_corpus(q: Optional[str] = None, user: dict = Depends(get_current_user)):
    items = await db.corpus.find({}, {"_id": 0}).to_list(1000)
    if q:
        ql = q.lower()
        items = [r for r in items if ql in json.dumps(r).lower()]
    return items

def score_record(text: str, record: dict) -> int:
    tl = text.lower()
    score = 0
    for kw in record.get("keywords", []):
        if kw.lower() in tl:
            score += 3
    for field in ("symptom", "system", "make", "model", "engine"):
        val = str(record.get(field, "")).lower()
        for word in re.findall(r"[a-z0-9]{4,}", val):
            if word in tl:
                score += 1
    return score

async def match_corpus(text: str, aircraft: Optional[dict], limit: int = 4):
    records = await db.corpus.find({}, {"_id": 0}).to_list(1000)
    scored = []
    for r in records:
        s = score_record(text, r)
        if aircraft:
            if aircraft.get("make") and aircraft["make"].lower() in (r.get("make", "").lower() + r.get("engine", "").lower()):
                s += 2
            if aircraft.get("model") and r.get("model", "").lower() and r["model"].lower() in aircraft["model"].lower():
                s += 2
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in scored[:limit]]

def search_manuals(text: str, manuals: List[dict], limit: int = 3):
    tl = text.lower()
    terms = [w for w in re.findall(r"[a-z0-9]{4,}", tl)]
    hits = []
    for m in manuals:
        for p in m.get("pages", []):
            pt = p["text"].lower()
            score = sum(pt.count(t) for t in terms)
            if score > 0:
                excerpt = p["text"].strip().replace("\n", " ")
                hits.append((score, {
                    "doc_name": m.get("doc_name"), "doc_type": m.get("doc_type"),
                    "ata": m.get("ata"), "status": m.get("status"),
                    "page": p["page"], "excerpt": excerpt[:900],
                }))
    hits.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in hits[:limit]]

# ---------------------------------------------------------------------------
# Logbook
# ---------------------------------------------------------------------------
@api_router.get("/logbook")
async def list_logbook(aircraft_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {"user_id": user["id"]}
    if aircraft_id:
        q["aircraft_id"] = aircraft_id
    items = await db.logbook.find(q, {"_id": 0}).sort("date", -1).to_list(1000)
    return items

@api_router.post("/logbook")
async def create_logbook(payload: LogbookInput, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc.update({"id": str(uuid.uuid4()), "user_id": user["id"],
                "created_at": datetime.now(timezone.utc).isoformat()})
    await db.logbook.insert_one(dict(doc))
    return clean(doc)

@api_router.delete("/logbook/{entry_id}")
async def delete_logbook(entry_id: str, user: dict = Depends(get_current_user)):
    await db.logbook.delete_one({"id": entry_id, "user_id": user["id"]})
    return {"ok": True}

# ---------------------------------------------------------------------------
# Chat sessions
# ---------------------------------------------------------------------------
@api_router.get("/sessions")
async def list_sessions(user: dict = Depends(get_current_user)):
    items = await db.sessions.find({"user_id": user["id"]}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return items

@api_router.post("/sessions")
async def create_session(payload: SessionInput, user: dict = Depends(get_current_user)):
    doc = {"id": str(uuid.uuid4()), "user_id": user["id"], "title": payload.title,
           "aircraft_id": payload.aircraft_id,
           "created_at": datetime.now(timezone.utc).isoformat(),
           "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.sessions.insert_one(dict(doc))
    return clean(doc)

@api_router.put("/sessions/{session_id}")
async def update_session(session_id: str, payload: SessionInput, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.sessions.update_one({"id": session_id, "user_id": user["id"]}, {"$set": updates})
    doc = await db.sessions.find_one({"id": session_id}, {"_id": 0})
    return doc

@api_router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(get_current_user)):
    await db.sessions.delete_one({"id": session_id, "user_id": user["id"]})
    await db.messages.delete_many({"session_id": session_id})
    return {"ok": True}

@api_router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, user: dict = Depends(get_current_user)):
    items = await db.messages.find({"session_id": session_id, "user_id": user["id"]},
                                   {"_id": 0}).sort("created_at", 1).to_list(1000)
    return items

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
def build_system_prompt(aircraft, manual_hits, corpus_hits, has_manuals):
    lines = []
    lines.append(
        "You are Squawk King IA, an expert aircraft maintenance troubleshooting agent for piston "
        "training aircraft (Cessna 152/172/182; Piper PA-28/PA-34/PA-44; Lycoming IO-360/IO-320/O-360/O-320; "
        "Rotax 912-series). You speak mechanic-first: direct, technical, no fluff."
    )
    lines.append("\n=== RESPONSE FORMAT (STRICT) ===")
    lines.append(
        "1. Start with ONE sentence stating the single MOST LIKELY cause of the reported symptom.\n"
        "2. Ask AT MOST two clarifying questions, and ONLY if genuinely needed to proceed.\n"
        "3. Provide numbered troubleshooting steps in the correct diagnostic sequence. For each step give the "
        "expected result and a decision point (what to do if pass/fail).\n"
        "4. End with the NEXT most likely cause to pursue if the first path clears.\n"
        "Use Markdown. Keep it tight and actionable."
    )
    lines.append("\n=== APPROVED-DATA RULE (CRITICAL) ===")
    lines.append(
        "Final AIRCRAFT-SPECIFIC maintenance guidance may come ONLY from applicable current approved sources "
        "(AMM, maintenance/service manuals, ICA, wiring diagrams, TCDS, ADs, manufacturer troubleshooting guides). "
        "EVERY aircraft-specific instruction MUST cite the document name AND ATA chapter-section-subject, e.g. "
        "[Cessna 172 SMM, ATA 74-00-00]. Treat the current applicable source as controlling; if a superseded "
        "source is present, show it as HISTORICAL ONLY and briefly explain the material change and why the current "
        "guidance prevails."
    )
    lines.append(
        "You MAY give clearly-labeled 'Preliminary Reasoning (not aircraft-specific)' before applicability is "
        "confirmed. Do NOT give aircraft-specific maintenance steps until ALL of these are confirmed: make, model, "
        "year of manufacture, serial number, configuration, AND applicable approved references are available."
    )
    lines.append(
        f"If aircraft-specific guidance is required but the required approved data is UNAVAILABLE, STOP without "
        f"guessing and output EXACTLY this line and nothing else after it:\n{STOP_MESSAGE}"
    )

    lines.append("\n=== AIRCRAFT PROFILE STATUS ===")
    if aircraft:
        fields = {
            "make": aircraft.get("make"), "model": aircraft.get("model"),
            "year": aircraft.get("year"), "serial_number": aircraft.get("serial_number"),
            "configuration": aircraft.get("configuration"),
        }
        missing = [k for k, v in fields.items() if not v]
        lines.append(f"Selected aircraft: {json.dumps(fields)}")
        lines.append(f"Profile confirmed flag: {aircraft.get('confirmed')}")
        lines.append(f"Missing identity fields: {missing if missing else 'none'}")
    else:
        lines.append("No aircraft selected. Applicability is NOT confirmed. Preliminary reasoning only.")

    lines.append("\n=== APPROVED SOURCE EXCERPTS (controlling data) ===")
    if manual_hits:
        for h in manual_hits:
            tag = "HISTORICAL/SUPERSEDED" if h.get("status") == "superseded" else "CURRENT"
            lines.append(f"[{tag}] {h['doc_name']} ({h.get('doc_type')}) ATA {h.get('ata') or 'n/a'} p.{h['page']}:\n\"{h['excerpt']}\"")
    else:
        lines.append("NO approved manual excerpts matched this symptom for the selected aircraft.")
    lines.append(f"Approved manuals available for this aircraft: {has_manuals}")

    lines.append("\n=== HISTORICAL REFERENCE CORPUS (for symptom matching & prioritization ONLY) ===")
    lines.append(
        "Use these ONLY to improve symptom matching and to prioritize likely causes. They are NOT approved "
        "sources and must NEVER be cited as maintenance authority."
    )
    if corpus_hits:
        for r in corpus_hits:
            lines.append(f"- {r['make']} {r['model']} / {r.get('engine')} | ATA {r.get('ata')} | Symptom: {r['symptom']} | Prior likely cause: {r['likely_cause']}")
    else:
        lines.append("- No close historical matches found.")
    return "\n".join(lines)

async def stream_chat(session_id: str, user: dict, text: str):
    session = await db.sessions.find_one({"id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    aircraft = None
    if session.get("aircraft_id"):
        aircraft = await db.aircraft.find_one({"id": session["aircraft_id"]}, {"_id": 0})

    manual_q = {"user_id": user["id"], "is_deleted": False}
    if aircraft:
        manual_q["aircraft_id"] = aircraft["id"]
    manuals = await db.manuals.find(manual_q).to_list(200)
    has_manuals = len(manuals) > 0
    manual_hits = search_manuals(text, manuals)
    corpus_hits = await match_corpus(text, aircraft)

    system_prompt = build_system_prompt(aircraft, manual_hits, corpus_hits, has_manuals)

    history = await db.messages.find({"session_id": session_id}, {"_id": 0}).sort("created_at", 1).to_list(1000)
    convo = ""
    for m in history[-10:]:
        role = "MECHANIC" if m["role"] == "user" else "SQUAWK KING IA"
        convo += f"\n{role}: {m['content']}"
    user_payload = text if not convo else f"Recent conversation:{convo}\n\nMECHANIC (new message): {text}"

    now = datetime.now(timezone.utc).isoformat()
    await db.messages.insert_one({"id": str(uuid.uuid4()), "session_id": session_id, "user_id": user["id"],
                                  "role": "user", "content": text, "created_at": now})
    citations = [{"doc_name": h["doc_name"], "ata": h.get("ata"), "page": h["page"],
                  "status": h.get("status"), "doc_type": h.get("doc_type")} for h in manual_hits]

    chat = LlmChat(api_key=EMERGENT_KEY, session_id=session_id, system_message=system_prompt).with_model("openai", "gpt-5.4")

    async def gen():
        full = ""
        meta = {"citations": citations,
                "corpus": [{"make": r["make"], "model": r["model"], "ata": r.get("ata"),
                            "symptom": r["symptom"], "likely_cause": r["likely_cause"]} for r in corpus_hits]}
        yield f"data: {json.dumps({'type': 'meta', 'meta': meta})}\n\n"
        try:
            async for event in chat.stream_message(UserMessage(text=user_payload)):
                if isinstance(event, TextDelta):
                    full += event.content
                    yield f"data: {json.dumps({'type': 'delta', 'content': event.content})}\n\n"
                elif isinstance(event, StreamDone):
                    break
        except Exception as e:
            logger.error(f"LLM stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'content': 'AI generation failed: ' + str(e)})}\n\n"
        if full.strip():
            await db.messages.insert_one({"id": str(uuid.uuid4()), "session_id": session_id, "user_id": user["id"],
                                          "role": "assistant", "content": full,
                                          "citations": citations, "corpus": meta["corpus"],
                                          "created_at": datetime.now(timezone.utc).isoformat()})
            await db.sessions.update_one({"id": session_id}, {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}})
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@api_router.post("/sessions/{session_id}/message")
async def send_message(session_id: str, payload: MessageInput, user: dict = Depends(get_current_user)):
    return await stream_chat(session_id, user, payload.text)

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    admin_email = os.environ.get("ADMIN_EMAIL", "mechanic@squawkking.io")
    admin_password = os.environ.get("ADMIN_PASSWORD", "squawk123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one({"email": admin_email, "password_hash": hash_password(admin_password),
                                   "name": "Lead Mechanic", "role": "admin",
                                   "created_at": datetime.now(timezone.utc).isoformat()})
        existing = await db.users.find_one({"email": admin_email})
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})

    if await db.corpus.count_documents({}) == 0:
        await db.corpus.insert_many([dict(r, id=str(uuid.uuid4())) for r in HISTORICAL_RECORDS])
        logger.info("Seeded historical corpus")

    # Seed starter aircraft for admin user
    admin = await db.users.find_one({"email": admin_email})
    admin_id = str(admin["_id"])
    if await db.aircraft.count_documents({"user_id": admin_id}) == 0:
        for a in STARTER_AIRCRAFT:
            await db.aircraft.insert_one(dict(a, id=str(uuid.uuid4()), user_id=admin_id,
                                              created_at=datetime.now(timezone.utc).isoformat()))
        logger.info("Seeded starter aircraft")

    try:
        init_storage()
        logger.info("Storage initialized")
    except Exception as e:
        logger.error(f"Storage init failed: {e}")

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
    client.close()
