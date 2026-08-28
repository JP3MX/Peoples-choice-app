"""Squawk King IA - Billing / Stripe subscription regression tests.

Covers:
- GET /api/billing/plans (public shape: 3 plans, trial_days=3)
- GET /api/billing/status for fresh user (trial), admin (unlimited), and after DB backdate (paywall)
- POST /api/sessions/{id}/message returns 402 for expired trial (paywall detail text)
- POST /api/payments/checkout returns a real Stripe Checkout URL (checkout.stripe.com)
- GET /api/payments/status/{session_id} returns pending/paid shape
- Token exhaustion for Basic subscriber (backend-level 402 via DB simulation)
- /payment/cancel is a frontend route (no backend endpoint) — skipped here.
"""
import os
import re
import time
import uuid
import json
import requests
import pytest
from datetime import datetime, timedelta, timezone
from pymongo import MongoClient
from bson import ObjectId

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = os.environ["DEMO_EMAIL"]
DEMO_PASSWORD = os.environ["DEMO_PASSWORD"]

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


# --- session helpers --------------------------------------------------------
@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def admin_token(http):
    r = http.post(f"{API}/auth/login",
                  json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _register(http, email, password="pass1234"):
    r = http.post(f"{API}/auth/register",
                  json={"email": email, "password": password, "name": "TestUser"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


# --- 1. /billing/plans public ------------------------------------------------
def test_plans_public_shape(http):
    r = http.get(f"{API}/billing/plans")
    assert r.status_code == 200
    body = r.json()
    assert body["trial_days"] == 3
    plans = body["plans"]
    assert len(plans) == 3
    by_tier = {p["tier"]: p for p in plans}
    assert by_tier["basic"]["price"] == 19 and by_tier["basic"]["tokens"] == 5
    assert by_tier["basic"]["lookup_key"] == "sk_basic_monthly"
    assert by_tier["pro"]["price"] == 39 and by_tier["pro"]["tokens"] == 50
    assert by_tier["pro"]["lookup_key"] == "sk_pro_monthly"
    assert by_tier["unlimited"]["price"] == 79 and by_tier["unlimited"]["tokens"] is None
    assert by_tier["unlimited"]["lookup_key"] == "sk_unlimited_monthly"


# --- 2. Admin billing status is unlimited -----------------------------------
def test_admin_billing_unlimited(http, admin_token):
    r = http.get(f"{API}/billing/status",
                 headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    st = r.json()
    assert st["plan"] == "unlimited"
    assert st["allowed"] is True
    assert st["status"] == "active"


# --- 3. Fresh user is trial + allowed ---------------------------------------
def test_new_user_trial_status_and_can_chat(http):
    email = f"trial_{uuid.uuid4().hex[:8]}@example.com"
    tok = _register(http, email)
    r = http.get(f"{API}/billing/status", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    st = r.json()
    assert st["plan"] == "trial"
    assert st["trial_active"] is True
    assert st["allowed"] is True
    assert st["trial_days_left"] == 3
    # can send a chat message (no paywall)
    sess = http.post(f"{API}/sessions", json={"title": "TEST_billing_trial"},
                     headers={"Authorization": f"Bearer {tok}"})
    assert sess.status_code == 200
    sid = sess.json()["id"]
    with requests.post(f"{API}/sessions/{sid}/message",
                       headers={"Authorization": f"Bearer {tok}",
                                "Content-Type": "application/json"},
                       json={"text": "quick ping"},
                       stream=True, timeout=60) as r2:
        assert r2.status_code == 200, r2.text
        # consume a bit
        chunks = 0
        for _ in r2.iter_lines():
            chunks += 1
            if chunks > 5:
                break
    # cleanup
    http.delete(f"{API}/sessions/{sid}", headers={"Authorization": f"Bearer {tok}"})
    db.users.delete_one({"email": email})


# --- 4. Paywall: expired trial => 402 ----------------------------------------
def test_expired_trial_returns_402(http):
    email = f"exp_{uuid.uuid4().hex[:8]}@example.com"
    tok = _register(http, email)
    # backdate created_at by 4 days
    past = (datetime.now(timezone.utc) - timedelta(days=4)).isoformat()
    db.users.update_one({"email": email}, {"$set": {"created_at": past}})
    # billing_status should now show expired
    st = http.get(f"{API}/billing/status", headers={"Authorization": f"Bearer {tok}"}).json()
    assert st["plan"] == "none"
    assert st["allowed"] is False
    # message returns 402
    sess = http.post(f"{API}/sessions", json={"title": "TEST_paywall"},
                     headers={"Authorization": f"Bearer {tok}"})
    sid = sess.json()["id"]
    r = requests.post(f"{API}/sessions/{sid}/message",
                      headers={"Authorization": f"Bearer {tok}",
                               "Content-Type": "application/json"},
                      json={"text": "will this work?"},
                      timeout=30)
    assert r.status_code == 402, f"expected 402 got {r.status_code}: {r.text}"
    body = r.json()
    detail = body.get("detail", "")
    assert "free trial has ended" in detail.lower(), detail
    # cleanup
    http.delete(f"{API}/sessions/{sid}", headers={"Authorization": f"Bearer {tok}"})
    db.users.delete_one({"email": email})


# --- 5. Basic subscriber token exhaustion returns 402 -----------------------
def test_basic_token_exhaustion_returns_402(http):
    email = f"basicx_{uuid.uuid4().hex[:8]}@example.com"
    tok = _register(http, email)
    # simulate Basic active subscription with tokens_used=5
    now = datetime.now(timezone.utc).isoformat()
    db.users.update_one({"email": email},
                        {"$set": {"tier": "basic", "subscription_status": "active",
                                  "tokens_used": 5, "period_start": now}})
    st = http.get(f"{API}/billing/status", headers={"Authorization": f"Bearer {tok}"}).json()
    assert st["plan"] == "basic"
    assert st["allowed"] is False
    assert st["remaining"] == 0
    sess = http.post(f"{API}/sessions", json={"title": "TEST_basic_exhaust"},
                     headers={"Authorization": f"Bearer {tok}"})
    sid = sess.json()["id"]
    r = requests.post(f"{API}/sessions/{sid}/message",
                      headers={"Authorization": f"Bearer {tok}",
                               "Content-Type": "application/json"},
                      json={"text": "hello"},
                      timeout=30)
    assert r.status_code == 402
    detail = r.json().get("detail", "")
    assert "token" in detail.lower(), detail
    # cleanup
    http.delete(f"{API}/sessions/{sid}", headers={"Authorization": f"Bearer {tok}"})
    db.users.delete_one({"email": email})


# --- 6. Checkout returns real Stripe Checkout URL ---------------------------
@pytest.mark.parametrize("lookup", ["sk_basic_monthly", "sk_pro_monthly", "sk_unlimited_monthly"])
def test_checkout_creates_real_stripe_session(http, lookup):
    email = f"ck_{uuid.uuid4().hex[:8]}@example.com"
    tok = _register(http, email)
    r = http.post(f"{API}/payments/checkout",
                  json={"lookup_key": lookup, "origin_url": BASE_URL},
                  headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    url = body["checkout_url"]
    sid = body["session_id"]
    assert url.startswith("https://checkout.stripe.com/"), url
    assert sid.startswith("cs_"), sid
    # status endpoint should return pending shape
    st = http.get(f"{API}/payments/status/{sid}")
    assert st.status_code == 200
    j = st.json()
    assert j["session_id"] == sid
    assert j["payment_status"] in ("pending", "paid", "unpaid", "no_payment_required")
    db.users.delete_one({"email": email})


# --- 7. Unknown plan lookup returns 400 -------------------------------------
def test_checkout_unknown_lookup_400(http, admin_token):
    r = http.post(f"{API}/payments/checkout",
                  json={"lookup_key": "sk_bogus", "origin_url": BASE_URL},
                  headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 400


# --- 8. Checkout requires auth ----------------------------------------------
def test_checkout_requires_auth(http):
    r = http.post(f"{API}/payments/checkout",
                  json={"lookup_key": "sk_basic_monthly", "origin_url": BASE_URL})
    assert r.status_code == 401
