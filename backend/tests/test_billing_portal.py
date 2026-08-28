"""Squawk King IA - Billing Portal + Welcome Email regression tests (iteration 6).

Covers:
- Registration triggers welcome email (placeholder Resend key -> logged, not delivered)
- GET /api/billing/status includes can_manage boolean
  * can_manage=False for fresh trial user
  * can_manage=True after users.stripe_customer_id is set
- POST /api/billing/portal:
  * 401 without auth
  * 400 for user with no stripe_customer_id (message contains "No active subscription")
  * 200 with billing.stripe.com portal_url for user with real stripe test customer
"""
import os
import re
import time
import uuid
import subprocess
import requests
import pytest
import stripe
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = os.environ["DEMO_EMAIL"]
DEMO_PASSWORD = os.environ["DEMO_PASSWORD"]

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY") or None
if STRIPE_SECRET_KEY:
    stripe.api_key = STRIPE_SECRET_KEY

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]


@pytest.fixture(scope="module")
def http():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _register(http, email, password="pass1234", origin=None):
    body = {"email": email, "password": password, "name": "TestUser"}
    if origin:
        body["origin_url"] = origin
    r = http.post(f"{API}/auth/register", json=body)
    assert r.status_code == 200, r.text
    return r.json()["token"]


# --- 1. Welcome email log on register --------------------------------------
def test_register_logs_welcome_email():
    """With placeholder RESEND_API_KEY, registration should log a 'Would send Welcome...' line."""
    email = f"welcome_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register",
                      json={"email": email, "password": "pass1234",
                            "name": "WelcomeTester",
                            "origin_url": BASE_URL})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "token" in data and data["user"]["email"] == email
    # Give the fire-and-forget email task time to run
    time.sleep(1.5)
    # Grep the backend supervisor logs for the welcome line
    try:
        out = subprocess.check_output(
            ["bash", "-lc",
             f"grep -h -i 'welcome' /var/log/supervisor/backend.*.log 2>/dev/null | tail -n 200"],
            timeout=5).decode("utf-8", errors="ignore")
    except subprocess.CalledProcessError:
        out = ""
    assert email in out, (
        f"Expected welcome-email log line containing {email}; log tail:\n{out}")
    assert "Would send" in out or "welcome" in out.lower()
    db.users.delete_one({"email": email})


# --- 2. billing/status includes can_manage ----------------------------------
def test_billing_status_can_manage_false_for_trial(http):
    email = f"tstat_{uuid.uuid4().hex[:8]}@example.com"
    tok = _register(http, email)
    r = http.get(f"{API}/billing/status",
                 headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    st = r.json()
    assert "can_manage" in st, st
    assert st["can_manage"] is False
    assert st["plan"] == "trial"
    db.users.delete_one({"email": email})


def test_billing_status_can_manage_true_when_customer_id(http):
    email = f"tcust_{uuid.uuid4().hex[:8]}@example.com"
    tok = _register(http, email)
    # simulate stripe_customer_id set (as if webhook fired)
    db.users.update_one({"email": email}, {"$set": {"stripe_customer_id": "cus_fake_1234"}})
    r = http.get(f"{API}/billing/status",
                 headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    st = r.json()
    assert st["can_manage"] is True
    db.users.delete_one({"email": email})


# --- 3. billing/portal auth + no-subscription behaviour ---------------------
def test_portal_requires_auth(http):
    r = http.post(f"{API}/billing/portal", json={"return_url": BASE_URL})
    assert r.status_code == 401


def test_portal_400_without_subscription(http):
    email = f"nosub_{uuid.uuid4().hex[:8]}@example.com"
    tok = _register(http, email)
    r = http.post(f"{API}/billing/portal",
                  json={"return_url": BASE_URL},
                  headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 400, r.text
    detail = (r.json().get("detail") or "").lower()
    assert "no active subscription" in detail, detail
    db.users.delete_one({"email": email})


# --- 4. billing/portal returns real billing.stripe.com URL ------------------
@pytest.mark.skipif(not STRIPE_SECRET_KEY, reason="STRIPE_SECRET_KEY not set")
def test_portal_returns_stripe_url_with_real_customer(http):
    email = f"portalok_{uuid.uuid4().hex[:8]}@example.com"
    tok = _register(http, email)
    # create a real Stripe test customer
    cust = stripe.Customer.create(email=email, description="TEST_billing_portal")
    try:
        db.users.update_one(
            {"email": email},
            {"$set": {"stripe_customer_id": cust.id,
                      "tier": "basic", "subscription_status": "active"}})
        r = http.post(f"{API}/billing/portal",
                      json={"return_url": BASE_URL},
                      headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 200, r.text
        body = r.json()
        url = body.get("portal_url", "")
        assert url.startswith("https://billing.stripe.com/"), url
    finally:
        try:
            stripe.Customer.delete(cust.id)
        except Exception:
            pass
        db.users.delete_one({"email": email})


# --- 5. Regression: demo login still works, admin can_manage semantics ------
def test_demo_login_still_works(http):
    r = http.post(f"{API}/auth/login",
                  json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    st = http.get(f"{API}/billing/status",
                  headers={"Authorization": f"Bearer {tok}"}).json()
    assert st["plan"] == "unlimited"
    # can_manage reflects presence of stripe_customer_id on the admin doc
    assert "can_manage" in st
    assert isinstance(st["can_manage"], bool)
