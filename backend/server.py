from dotenv import load_dotenv
from pathlib import Path
import os

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import io
import re
import uuid
import json
import secrets
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional

import bcrypt
import jwt
import asyncio
import stripe
import resend
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

# OpenAI ChatGPT models selectable per session (label -> model id)
OPENAI_MODELS = [
    {"id": "gpt-5.4", "label": "GPT-5.4", "note": "Recommended — balanced reasoning"},
    {"id": "gpt-5.4-mini", "label": "GPT-5.4 Mini", "note": "Faster, lighter"},
    {"id": "gpt-5.5", "label": "GPT-5.5", "note": "Higher capability"},
    {"id": "gpt-5.6-terra", "label": "GPT-5.6 Terra", "note": "Latest flagship"},
    {"id": "gpt-5", "label": "GPT-5", "note": "General purpose"},
    {"id": "gpt-4.1", "label": "GPT-4.1", "note": "Legacy, reliable"},
    {"id": "gpt-4o", "label": "GPT-4o", "note": "Legacy omni"},
    {"id": "o3", "label": "o3", "note": "Deep reasoning"},
]
ALLOWED_MODEL_IDS = {m["id"] for m in OPENAI_MODELS}
DEFAULT_MODEL = "gpt-5.4"

# --- Billing / subscription config ---
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY") or "sk_test_emergent"
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
TRIAL_DAYS = 3

PLANS = [
    {"lookup_key": "sk_basic_monthly", "tier": "basic", "name": "Basic",
     "price": 19, "tokens": 5,
     "features": ["5 troubleshooting tokens / month", "Unlimited aircraft profiles",
                  "Manual uploads & ATA citations", "Logbook & media"]},
    {"lookup_key": "sk_pro_monthly", "tier": "pro", "name": "Pro",
     "price": 39, "tokens": 50,
     "features": ["50 troubleshooting tokens / month", "Everything in Basic",
                  "Priority historical-corpus matching", "Model selector (GPT-5.x)"]},
    {"lookup_key": "sk_unlimited_monthly", "tier": "unlimited", "name": "Unlimited",
     "price": 79, "tokens": None,
     "features": ["Unlimited troubleshooting guidance", "Everything in Pro",
                  "Best for busy shops & multi-mechanic use"]},
]
TIER_LIMITS = {p["tier"]: p["tokens"] for p in PLANS}
LOOKUP_TIER = {p["lookup_key"]: p["tier"] for p in PLANS}

def _parse_dt(s):
    if not s:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(s) if isinstance(s, str) else s
    except ValueError:
        return datetime.now(timezone.utc)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

async def get_entitlement(email: str) -> dict:
    doc = await db.users.find_one({"email": email})
    now = datetime.now(timezone.utc)
    if not doc:
        return {"plan": "none", "trial_active": False, "allowed": False, "limit": 0,
                "used": 0, "remaining": 0, "trial_days_left": 0, "status": "expired"}
    if doc.get("role") == "admin":
        return {"plan": "unlimited", "trial_active": False, "allowed": True, "limit": None,
                "used": 0, "remaining": None, "trial_days_left": 0, "status": "active"}
    tier = doc.get("tier")
    if tier in TIER_LIMITS and doc.get("subscription_status") == "active":
        ps = _parse_dt(doc.get("period_start")) if doc.get("period_start") else now
        used = doc.get("tokens_used", 0)
        if now - ps > timedelta(days=30):
            used = 0
            await db.users.update_one({"email": email},
                                      {"$set": {"tokens_used": 0, "period_start": now.isoformat()}})
        limit = TIER_LIMITS[tier]
        remaining = None if limit is None else max(0, limit - used)
        return {"plan": tier, "trial_active": False, "allowed": limit is None or used < limit,
                "limit": limit, "used": used, "remaining": remaining, "trial_days_left": 0,
                "status": "active"}
    created = _parse_dt(doc.get("created_at"))
    trial_end = created + timedelta(days=TRIAL_DAYS)
    trial_active = now < trial_end
    secs = (trial_end - now).total_seconds()
    days_left = max(0, -(-int(secs) // 86400)) if trial_active else 0
    return {"plan": "trial" if trial_active else "none", "trial_active": trial_active,
            "allowed": trial_active, "limit": None, "used": 0, "remaining": None,
            "trial_days_left": days_left, "trial_ends": trial_end.isoformat(),
            "status": "trialing" if trial_active else "expired"}

async def apply_subscription(session_id: str):
    tx = await db.payment_transactions.find_one({"session_id": session_id})
    if not tx:
        return
    tier = LOOKUP_TIER.get(tx.get("lookup_key"))
    uid = tx.get("user_id")
    if not tier or not uid:
        return
    try:
        oid = ObjectId(uid)
    except Exception:
        return
    now = datetime.now(timezone.utc).isoformat()
    set_fields = {
        "tier": tier, "subscription_status": "active", "tokens_used": 0,
        "period_start": now, "stripe_subscription_id": tx.get("stripe_subscription_id"),
        "updated_at": now}
    if tx.get("stripe_customer_id"):
        set_fields["stripe_customer_id"] = tx["stripe_customer_id"]
    await db.users.update_one({"_id": oid}, {"$set": set_fields})

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

def delete_object(path: str) -> None:
    """Best-effort permanent removal used by account deletion."""
    key = init_storage()
    resp = requests.delete(f"{STORAGE_URL}/objects/{path}", headers={"X-Storage-Key": key}, timeout=60)
    if resp.status_code not in (200, 202, 204, 404):
        resp.raise_for_status()

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
    origin_url: Optional[str] = None

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
    model: Optional[str] = None

class MessageInput(BaseModel):
    text: str

class ReportInput(BaseModel):
    message_id: str
    session_id: str
    reason: str = "unsafe_or_incorrect"
    details: str = ""

class DeleteAccountInput(BaseModel):
    password: str

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
    asyncio.create_task(asyncio.to_thread(send_welcome_email, email, doc["name"], (payload.origin_url or "").rstrip("/")))
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

@api_router.post("/reports")
async def report_ai_response(payload: ReportInput, user: dict = Depends(get_current_user)):
    message = await db.messages.find_one({
        "id": payload.message_id,
        "session_id": payload.session_id,
        "user_id": user["id"],
        "role": "assistant",
    })
    if not message:
        raise HTTPException(status_code=404, detail="AI response not found")
    report = {
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "message_id": payload.message_id,
        "session_id": payload.session_id,
        "reason": payload.reason[:100],
        "details": payload.details[:2000],
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.ai_reports.insert_one(report)
    report.pop("_id", None)
    return {"ok": True, "report_id": report["id"]}

@api_router.delete("/auth/account")
async def delete_account(payload: DeleteAccountInput, user: dict = Depends(get_current_user)):
    stored_user = await db.users.find_one({"_id": ObjectId(user["id"])})
    if not stored_user or not verify_password(payload.password, stored_user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Password is incorrect")

    subscription_id = stored_user.get("stripe_subscription_id")
    if subscription_id and stripe.api_key and not stripe.api_key.startswith("sk_test_emergent"):
        try:
            await asyncio.to_thread(stripe.Subscription.cancel, subscription_id)
        except stripe.error.StripeError as exc:
            logger.error("Could not cancel Stripe subscription during account deletion: %s", exc)
            raise HTTPException(status_code=502, detail="Subscription cancellation failed. Account was not deleted.")

    owned_files = []
    for collection_name in ("manuals", "media"):
        docs = await db[collection_name].find({"user_id": user["id"]}, {"storage_path": 1}).to_list(10000)
        owned_files.extend(d.get("storage_path") for d in docs if d.get("storage_path"))

    for storage_path in owned_files:
        try:
            await asyncio.to_thread(delete_object, storage_path)
        except Exception as exc:
            logger.error("Could not delete stored object %s: %s", storage_path, exc)
            raise HTTPException(status_code=502, detail="Stored-file deletion failed. Account was not deleted.")

    user_collections = (
        "aircraft", "manuals", "media", "logbook", "sessions", "messages",
        "payment_transactions", "ai_reports",
    )
    for collection_name in user_collections:
        await db[collection_name].delete_many({"user_id": user["id"]})
    await db.password_reset_tokens.delete_many({"email": user["email"]})
    await db.users.delete_one({"_id": ObjectId(user["id"])})
    return {"ok": True}

RESET_TTL_MIN = 30
RESET_RATE_MAX = 3
RESET_RATE_WINDOW_MIN = 15
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM = os.environ.get("RESEND_FROM", "onboarding@resend.dev")
RESEND_FROM_NAME = os.environ.get("RESEND_FROM_NAME", "Squawk King IA")

def _resend_configured() -> bool:
    return bool(RESEND_API_KEY) and not RESEND_API_KEY.startswith("re_placeholder")

def _email_shell(title: str, body_html: str) -> str:
    return f"""
    <div style="font-family:Arial,Helvetica,sans-serif;background:#050505;padding:32px;color:#fff">
      <div style="max-width:520px;margin:0 auto;background:#0a0a0a;border:1px solid #262626">
        <div style="padding:24px;border-bottom:1px solid #262626">
          <span style="font-weight:900;letter-spacing:1px;text-transform:uppercase">Squawk King IA</span>
          <span style="color:#FF4F00;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin-left:8px">Maintenance Agent</span>
        </div>
        <div style="padding:28px 24px">
          <h1 style="font-size:20px;margin:0 0 12px">{title}</h1>
          {body_html}
        </div>
        <div style="padding:16px 24px;border-top:1px solid #262626;color:#555;font-size:11px">
          Squawk King IA · Piston-aircraft maintenance troubleshooting
        </div>
      </div>
    </div>"""

def _send_email(to_email: str, subject: str, html: str, tag: str = "email") -> bool:
    if not _resend_configured():
        logger.warning(f"[{tag}] Resend not configured (placeholder key). Would send '{subject}' to {to_email}")
        return False
    try:
        resend.api_key = RESEND_API_KEY
        resend.Emails.send({
            "from": f"{RESEND_FROM_NAME} <{RESEND_FROM}>",
            "to": [to_email], "subject": subject, "html": html,
        })
        logger.info(f"[{tag}] email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"[{tag}] Resend send failed for {to_email}: {e}")
        return False

def send_reset_email(to_email: str, link: str) -> bool:
    body = f"""
      <p style="color:#a3a3a3;line-height:1.6;margin:0 0 24px">
        We received a request to reset your Squawk King IA password. This link expires in {RESET_TTL_MIN} minutes and can be used once.
      </p>
      <a href="{link}" style="display:inline-block;background:#FF4F00;color:#fff;text-decoration:none;padding:14px 28px;font-weight:600;text-transform:uppercase;letter-spacing:1px;font-size:13px">Reset Password</a>
      <p style="color:#666;font-size:12px;margin:24px 0 0;word-break:break-all">Or paste this link: {link}</p>
      <p style="color:#666;font-size:12px;margin:16px 0 0">If you didn't request this, you can safely ignore this email.</p>"""
    html = _email_shell("Reset your password", body)
    sent = _send_email(to_email, "Reset your Squawk King IA password", html, tag="reset")
    if not sent:
        logger.warning(f"[reset] Reset link for {to_email}: {link}")
    return sent

def send_welcome_email(to_email: str, name: str, app_url: str = "") -> bool:
    cta = f'<a href="{app_url}" style="display:inline-block;background:#007AFF;color:#fff;text-decoration:none;padding:14px 28px;font-weight:600;text-transform:uppercase;letter-spacing:1px;font-size:13px">Open the hangar</a>' if app_url else ""
    body = f"""
      <p style="color:#a3a3a3;line-height:1.6;margin:0 0 16px">Welcome aboard, {name}.</p>
      <p style="color:#a3a3a3;line-height:1.6;margin:0 0 20px">
        Your Squawk King IA account is ready. You're on a <strong style="color:#fff">3-day free trial</strong> with full troubleshooting access —
        describe a squawk and get the most-likely cause first, sequenced steps, and citations to approved manuals with ATA chapters.
      </p>
      <ul style="color:#a3a3a3;line-height:1.7;margin:0 0 22px;padding-left:18px">
        <li>Confirm your aircraft (make, model, year, serial, configuration)</li>
        <li>Upload approved manuals (AMM, service manuals, ADs) for cited guidance</li>
        <li>Keep a logbook and attach photos to each squawk</li>
      </ul>
      {cta}
      <p style="color:#666;font-size:12px;margin:22px 0 0">Fly safe — the Squawk King IA crew</p>"""
    html = _email_shell("Welcome to Squawk King IA", body)
    return _send_email(to_email, "Welcome to Squawk King IA", html, tag="welcome")

class ForgotInput(BaseModel):
    email: EmailStr
    origin_url: Optional[str] = None

class ResetInput(BaseModel):
    token: str
    new_password: str

class ChangePwInput(BaseModel):
    current_password: str
    new_password: str

@api_router.post("/auth/forgot-password")
async def forgot_password(payload: ForgotInput):
    email = payload.email.lower()
    now = datetime.now(timezone.utc)
    window_start = (now - timedelta(minutes=RESET_RATE_WINDOW_MIN)).isoformat()
    # Bounded-growth cleanup: drop stale rate rows and expired/used reset tokens.
    await db.reset_attempts.delete_many({"ts": {"$lt": window_start}})
    await db.password_reset_tokens.delete_many(
        {"$or": [{"used": True}, {"expires_at": {"$lt": now.isoformat()}}]})
    recent = await db.reset_attempts.count_documents({"email": email, "ts": {"$gte": window_start}})
    if recent >= RESET_RATE_MAX:
        raise HTTPException(status_code=429,
                            detail="Too many reset requests. Please wait a few minutes and try again.")
    await db.reset_attempts.insert_one({"email": email, "ts": now.isoformat()})

    generic = {"message": "If an account with that email exists, a password reset link has been sent."}
    user = await db.users.find_one({"email": email})
    if not user:
        return generic

    token = secrets.token_urlsafe(32)
    expires = now + timedelta(minutes=RESET_TTL_MIN)
    await db.password_reset_tokens.delete_many({"email": email})
    await db.password_reset_tokens.insert_one({
        "email": email, "token": token, "expires_at": expires.isoformat(),
        "used": False, "created_at": now.isoformat(),
    })
    origin = (payload.origin_url or "").rstrip("/") or os.environ.get("CORS_ORIGINS", "").split(",")[0].rstrip("/")
    link = f"{origin}/reset?token={token}"
    send_reset_email(email, link)
    return generic

@api_router.post("/auth/reset-password")
async def reset_password(payload: ResetInput):
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    rec = await db.password_reset_tokens.find_one({"token": payload.token.strip()})
    if not rec or rec.get("used"):
        raise HTTPException(status_code=400, detail="This reset link is invalid or has already been used.")
    if datetime.fromisoformat(rec["expires_at"]) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This reset link has expired. Request a new one.")
    await db.users.update_one({"email": rec["email"]},
                              {"$set": {"password_hash": hash_password(payload.new_password)}})
    await db.password_reset_tokens.update_one({"_id": rec["_id"]}, {"$set": {"used": True}})
    return {"ok": True, "message": "Password updated. You can now sign in."}

@api_router.post("/auth/change-password")
async def change_password(payload: ChangePwInput, user: dict = Depends(get_current_user)):
    if len(payload.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")
    dbuser = await db.users.find_one({"email": user["email"]})
    if not dbuser.get("password_hash") or not verify_password(payload.current_password, dbuser["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    await db.users.update_one({"email": user["email"]},
                              {"$set": {"password_hash": hash_password(payload.new_password)}})
    return {"ok": True, "message": "Password changed successfully"}

EMERGENT_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

@api_router.post("/auth/google/session")
async def google_session(request: Request):
    session_id = request.headers.get("X-Session-ID")
    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session id")
    try:
        resp = await asyncio.to_thread(
            requests.get, EMERGENT_SESSION_URL,
            headers={"X-Session-ID": session_id}, timeout=30)
    except Exception as e:
        logger.error(f"[google-auth] session-data request failed: {e}")
        raise HTTPException(status_code=502, detail="Auth service unavailable")
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid or expired Google session")
    data = resp.json()
    email = (data.get("email") or "").lower()
    if not email:
        raise HTTPException(status_code=401, detail="Google session missing email")
    name = data.get("name") or "Mechanic"
    picture = data.get("picture")
    now = datetime.now(timezone.utc).isoformat()
    user = await db.users.find_one({"email": email})
    if not user:
        doc = {"email": email, "password_hash": None, "name": name, "role": "mechanic",
               "auth_provider": "google", "picture": picture, "created_at": now}
        res = await db.users.insert_one(doc)
        uid = str(res.inserted_id)
        asyncio.create_task(asyncio.to_thread(send_welcome_email, email, name, ""))
    else:
        uid = str(user["_id"])
        updates = {}
        if picture and user.get("picture") != picture:
            updates["picture"] = picture
        if not user.get("auth_provider"):
            updates["auth_provider"] = "google"
        if updates:
            await db.users.update_one({"_id": user["_id"]}, {"$set": updates})
        name = user.get("name", name)
    token = create_access_token(uid, email)
    return {"token": token, "user": {"id": uid, "email": email, "name": name,
                                     "role": "mechanic", "picture": picture}}

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
# Media & file storage (photos, part/wiring images, misc files per aircraft)
# ---------------------------------------------------------------------------
IMAGE_EXTS = {"jpg", "jpeg", "png", "gif", "webp", "heic", "heif", "bmp"}

@api_router.get("/media")
async def list_media(aircraft_id: Optional[str] = None, user: dict = Depends(get_current_user)):
    q = {"user_id": user["id"], "is_deleted": False}
    if aircraft_id:
        q["aircraft_id"] = aircraft_id
    items = await db.media.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return items

@api_router.post("/media")
async def upload_media(
    file: UploadFile = File(...),
    aircraft_id: str = Form(""),
    caption: str = Form(""),
    user: dict = Depends(get_current_user),
):
    data = await file.read()
    ext = file.filename.split(".")[-1].lower() if "." in file.filename else "bin"
    path = f"{APP_NAME}/media/{user['id']}/{uuid.uuid4()}.{ext}"
    try:
        put_object(path, data, file.content_type or "application/octet-stream")
    except Exception as e:
        logger.error(f"media upload failed: {e}")
        raise HTTPException(status_code=502, detail="File storage upload failed")
    ct = file.content_type or "application/octet-stream"
    kind = "image" if ct.startswith("image/") or ext in IMAGE_EXTS else "file"
    doc = {
        "id": str(uuid.uuid4()), "user_id": user["id"], "aircraft_id": aircraft_id or None,
        "storage_path": path, "original_filename": file.filename, "caption": caption,
        "content_type": ct, "size": len(data), "kind": kind, "is_deleted": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.media.insert_one(dict(doc))
    return clean(doc)

@api_router.delete("/media/{media_id}")
async def delete_media(media_id: str, user: dict = Depends(get_current_user)):
    res = await db.media.update_one({"id": media_id, "user_id": user["id"], "is_deleted": False},
                                    {"$set": {"is_deleted": True}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Media not found")
    return {"ok": True}

@api_router.get("/media/{media_id}/download")
async def download_media(media_id: str, authorization: str = Header(None), auth: str = Query(None)):
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
    record = await db.media.find_one({"id": media_id, "user_id": payload["sub"], "is_deleted": False})
    if not record:
        raise HTTPException(status_code=404, detail="Media not found")
    data, content_type = get_object(record["storage_path"])
    return Response(content=data, media_type=record.get("content_type", content_type),
                    headers={"Content-Disposition": f'inline; filename="{record["original_filename"]}"'})
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

@api_router.get("/models")
async def list_models(user: dict = Depends(get_current_user)):
    return {"models": OPENAI_MODELS, "default": DEFAULT_MODEL}

@api_router.post("/sessions")
async def create_session(payload: SessionInput, user: dict = Depends(get_current_user)):
    model = payload.model if payload.model in ALLOWED_MODEL_IDS else DEFAULT_MODEL
    doc = {"id": str(uuid.uuid4()), "user_id": user["id"], "title": payload.title,
           "aircraft_id": payload.aircraft_id, "model": model,
           "created_at": datetime.now(timezone.utc).isoformat(),
           "updated_at": datetime.now(timezone.utc).isoformat()}
    await db.sessions.insert_one(dict(doc))
    return clean(doc)

@api_router.put("/sessions/{session_id}")
async def update_session(session_id: str, payload: SessionInput, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if "model" in updates and updates["model"] not in ALLOWED_MODEL_IDS:
        updates.pop("model")
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

    ent = await get_entitlement(user["email"])
    if not ent["allowed"]:
        if ent["plan"] in ("trial", "none"):
            detail = "Your free trial has ended. Choose a plan to continue troubleshooting."
        else:
            detail = "You've used all troubleshooting tokens for this period. Upgrade your plan to continue."
        raise HTTPException(status_code=402, detail=detail)

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

    chat = LlmChat(api_key=EMERGENT_KEY, session_id=session_id, system_message=system_prompt)
    model = session.get("model") if session.get("model") in ALLOWED_MODEL_IDS else DEFAULT_MODEL
    chat.with_model("openai", model)

    async def gen():
        full = ""
        meta = {"citations": citations,
                "model": model,
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
        assistant_message_id = None
        if full.strip():
            assistant_message_id = str(uuid.uuid4())
            await db.messages.insert_one({"id": assistant_message_id, "session_id": session_id, "user_id": user["id"],
                                          "role": "assistant", "content": full,
                                          "citations": citations, "corpus": meta["corpus"],
                                          "created_at": datetime.now(timezone.utc).isoformat()})
            await db.sessions.update_one({"id": session_id}, {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}})
            if ent["plan"] in TIER_LIMITS and TIER_LIMITS.get(ent["plan"]) is not None:
                await db.users.update_one({"email": user["email"]}, {"$inc": {"tokens_used": 1}})
        yield f"data: {json.dumps({'type': 'done', 'message_id': assistant_message_id})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@api_router.post("/sessions/{session_id}/message")
async def send_message(session_id: str, payload: MessageInput, user: dict = Depends(get_current_user)):
    return await stream_chat(session_id, user, payload.text)

# ---------------------------------------------------------------------------
# Billing & Stripe payments
# ---------------------------------------------------------------------------
class CheckoutRequest(BaseModel):
    lookup_key: str
    origin_url: str

@api_router.get("/billing/plans")
async def billing_plans():
    return {"plans": PLANS, "trial_days": TRIAL_DAYS}

@api_router.get("/billing/status")
async def billing_status(user: dict = Depends(get_current_user)):
    ent = await get_entitlement(user["email"])
    ent["plans"] = PLANS
    ent["trial_days"] = TRIAL_DAYS
    dbuser = await db.users.find_one({"email": user["email"]})
    ent["can_manage"] = bool(dbuser and dbuser.get("stripe_customer_id"))
    return ent

@api_router.post("/payments/checkout")
async def create_checkout(req: CheckoutRequest, user: dict = Depends(get_current_user)):
    if req.lookup_key not in LOOKUP_TIER:
        raise HTTPException(status_code=400, detail="Unknown plan")
    prices = await asyncio.to_thread(
        lambda: stripe.Price.list(lookup_keys=[req.lookup_key], active=True, limit=1).data)
    if not prices:
        raise HTTPException(status_code=500, detail=f"Price not configured: {req.lookup_key}")
    price = prices[0]
    origin = req.origin_url.rstrip("/")
    def _create():
        return stripe.checkout.Session.create(
            line_items=[{"price": price.id, "quantity": 1}],
            mode="subscription",
            success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{origin}/payment/cancel",
            metadata={"user_id": user["id"], "lookup_key": req.lookup_key},
            subscription_data={"metadata": {"user_id": user["id"], "lookup_key": req.lookup_key}},
            managed_payments={"enabled": True},
        )
    try:
        session = await asyncio.to_thread(_create)
    except stripe.error.InvalidRequestError as e:
        msg = (getattr(e, "user_message", "") or "").lower()
        if "managed payments" in msg or "ineligible" in msg:
            def _create_tax():
                return stripe.checkout.Session.create(
                    line_items=[{"price": price.id, "quantity": 1}],
                    mode="subscription",
                    success_url=f"{origin}/payment/success?session_id={{CHECKOUT_SESSION_ID}}",
                    cancel_url=f"{origin}/payment/cancel",
                    metadata={"user_id": user["id"], "lookup_key": req.lookup_key},
                    subscription_data={"metadata": {"user_id": user["id"], "lookup_key": req.lookup_key}},
                    automatic_tax={"enabled": True}, billing_address_collection="required",
                )
            session = await asyncio.to_thread(_create_tax)
        else:
            raise HTTPException(status_code=502, detail="Stripe checkout failed")
    await db.payment_transactions.insert_one({
        "session_id": session.id, "user_id": user["id"], "lookup_key": req.lookup_key,
        "amount": (price.unit_amount or 0) / 100.0, "currency": price.currency,
        "status": "initiated", "payment_status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return {"checkout_url": session.url, "session_id": session.id}

@api_router.get("/payments/status/{session_id}")
async def payment_status(session_id: str):
    record = await db.payment_transactions.find_one({"session_id": session_id})
    if not record:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if record.get("payment_status") != "paid":
        try:
            s = await asyncio.to_thread(stripe.checkout.Session.retrieve, session_id)
            if s.payment_status == "paid" or s.status == "complete":
                await db.payment_transactions.update_one(
                    {"session_id": session_id, "payment_status": {"$ne": "paid"}},
                    {"$set": {"status": "completed", "payment_status": "paid",
                              "stripe_subscription_id": s.subscription,
                              "stripe_customer_id": s.customer,
                              "updated_at": datetime.now(timezone.utc).isoformat()}})
                await apply_subscription(session_id)
                record = await db.payment_transactions.find_one({"session_id": session_id})
        except stripe.error.StripeError:
            pass
    return {"session_id": record["session_id"], "status": record["status"],
            "payment_status": record["payment_status"]}

@api_router.post("/stripe/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
    except (stripe.error.SignatureVerificationError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid signature")
    obj, t = event["data"]["object"], event["type"]
    if t == "checkout.session.completed":
        await db.payment_transactions.update_one(
            {"session_id": obj["id"], "payment_status": {"$ne": "paid"}},
            {"$set": {"status": "completed", "payment_status": obj.get("payment_status", "paid"),
                      "stripe_subscription_id": obj.get("subscription"),
                      "stripe_customer_id": obj.get("customer"),
                      "updated_at": datetime.now(timezone.utc).isoformat()}})
        await apply_subscription(obj["id"])
    elif t == "checkout.session.expired":
        await db.payment_transactions.update_one({"session_id": obj["id"]},
            {"$set": {"status": "expired", "payment_status": "expired",
                      "updated_at": datetime.now(timezone.utc).isoformat()}})
    return {"status": "ok"}

class PortalRequest(BaseModel):
    return_url: str

@api_router.post("/billing/portal")
async def billing_portal(req: PortalRequest, user: dict = Depends(get_current_user)):
    dbuser = await db.users.find_one({"email": user["email"]})
    customer_id = dbuser.get("stripe_customer_id")
    if not customer_id:
        raise HTTPException(status_code=400,
                            detail="No active subscription to manage. Choose a plan first.")
    return_url = (req.return_url or "").rstrip("/") or os.environ.get("CORS_ORIGINS", "").split(",")[0]
    try:
        session = await asyncio.to_thread(
            lambda: stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url))
    except stripe.error.StripeError as e:
        logger.error(f"[portal] failed: {e}")
        raise HTTPException(status_code=502, detail="Could not open billing portal")
    return {"portal_url": session.url}

# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------
@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.password_reset_tokens.create_index("expires_at")
    await db.password_reset_tokens.create_index("token")
    await db.reset_attempts.create_index("ts")
    admin_email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if bool(admin_email) != bool(admin_password):
        raise RuntimeError("ADMIN_EMAIL and ADMIN_PASSWORD must either both be set or both be omitted")
    admin = None
    if admin_email:
        if len(admin_password) < 16:
            raise RuntimeError("ADMIN_PASSWORD must be at least 16 characters")
        existing = await db.users.find_one({"email": admin_email})
        if existing is None:
            result = await db.users.insert_one({
                "email": admin_email,
                "password_hash": hash_password(admin_password),
                "name": "Lead Mechanic",
                "role": "admin",
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
            admin = await db.users.find_one({"_id": result.inserted_id})
        else:
            admin = existing
            if admin.get("role") != "admin":
                await db.users.update_one({"_id": admin["_id"]}, {"$set": {"role": "admin"}})

    if await db.corpus.count_documents({}) == 0:
        await db.corpus.insert_many([dict(r, id=str(uuid.uuid4())) for r in HISTORICAL_RECORDS])
        logger.info("Seeded historical corpus")

    # Seed starter aircraft only when an explicit admin account is configured.
    if admin:
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
