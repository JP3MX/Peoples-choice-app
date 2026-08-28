"""Squawk King IA — Google (Emergent) auth + regression tests.

Covers:
- POST /api/auth/google/session guards:
    * missing X-Session-ID -> 400 (no user created)
    * bogus X-Session-ID -> 401 (no user created)
- Seeded Google user path (mint app JWT per /app/auth_testing.md):
    * GET /api/auth/me returns the user
    * GET /api/billing/status -> plan="trial", trial_active=true, allowed=true
- Google user paywall regression: backdate created_at >3d -> chat POST 402
- Regression:
    * password login for demo mechanic still works
    * password login for a Google user (password_hash=None) returns 401, not 500
    * change-password endpoint returns 400 (not 500) for a Google user
"""
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

# Load backend env (JWT_SECRET, MONGO_URL, DB_NAME) — required to mint app JWT
load_dotenv("/app/backend/.env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
JWT_SECRET = os.environ["JWT_SECRET"]

DEMO_EMAIL = os.environ["DEMO_EMAIL"]
DEMO_PASSWORD = os.environ["DEMO_PASSWORD"]

GOOGLE_EMAIL = "google.tester@example.com"


# --- helpers ----------------------------------------------------------------
@pytest.fixture(scope="session")
def mongo():
    client = MongoClient(os.environ["MONGO_URL"])
    yield client[os.environ["DB_NAME"]]
    client.close()


def _seed_google_user(mongo, email: str, name: str = "Google Tester") -> str:
    """Insert or fetch a Google-provider user, return string _id."""
    u = mongo.users.find_one({"email": email})
    if u:
        # ensure google provider + no password
        mongo.users.update_one(
            {"_id": u["_id"]},
            {"$set": {"auth_provider": "google", "password_hash": None,
                      "role": "mechanic"}},
        )
        return str(u["_id"])
    res = mongo.users.insert_one({
        "email": email, "password_hash": None, "name": name,
        "role": "mechanic", "auth_provider": "google",
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return str(res.inserted_id)


def _mint_jwt(uid: str, email: str) -> str:
    payload = {
        "sub": uid, "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


@pytest.fixture(scope="session")
def google_user(mongo):
    uid = _seed_google_user(mongo, GOOGLE_EMAIL)
    tok = _mint_jwt(uid, GOOGLE_EMAIL)
    yield {"id": uid, "email": GOOGLE_EMAIL, "token": tok}
    # cleanup at end of session
    mongo.users.delete_one({"email": GOOGLE_EMAIL})


# --- POST /api/auth/google/session guards -----------------------------------
def test_google_session_missing_header_returns_400(mongo):
    before = mongo.users.count_documents({})
    r = requests.post(f"{API}/auth/google/session", json={}, timeout=15)
    assert r.status_code == 400, r.text
    assert "session" in (r.json().get("detail", "").lower())
    after = mongo.users.count_documents({})
    assert after == before, "no user should be created on missing header"


def test_google_session_bogus_session_id_returns_401(mongo):
    before = mongo.users.count_documents({})
    bogus = f"bogus-{uuid.uuid4().hex}"
    r = requests.post(
        f"{API}/auth/google/session",
        json={},
        headers={"X-Session-ID": bogus},
        timeout=30,
    )
    # If Emergent returns non-200 -> backend maps to 401.
    # (502 is only used when the outbound HTTP call itself fails.)
    assert r.status_code == 401, r.text
    assert mongo.users.count_documents({}) == before, "no user created for bad session"


# --- Seeded Google user: /auth/me + /billing/status --------------------------
def test_google_user_me_returns_user(google_user):
    r = requests.get(
        f"{API}/auth/me",
        headers={"Authorization": f"Bearer {google_user['token']}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == GOOGLE_EMAIL
    assert body.get("id") == google_user["id"]


def test_google_user_billing_status_trial(google_user, mongo):
    # ensure created_at is recent (within trial window)
    mongo.users.update_one(
        {"email": GOOGLE_EMAIL},
        {"$set": {"created_at": datetime.now(timezone.utc).isoformat()}},
    )
    # ensure no stripe_customer_id/plan carrying over
    mongo.users.update_one(
        {"email": GOOGLE_EMAIL},
        {"$unset": {"stripe_customer_id": "", "plan": "", "subscription_status": ""}},
    )
    r = requests.get(
        f"{API}/billing/status",
        headers={"Authorization": f"Bearer {google_user['token']}"},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    ent = r.json()
    assert ent["plan"] == "trial", ent
    assert ent["trial_active"] is True, ent
    assert ent["allowed"] is True, ent


# --- Google user paywall regression -----------------------------------------
def test_google_user_paywall_after_trial(google_user, mongo):
    # backdate created_at > TRIAL_DAYS (3) -> expected paywall
    backdated = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    mongo.users.update_one(
        {"email": GOOGLE_EMAIL},
        {"$set": {"created_at": backdated}},
    )
    try:
        headers = {"Authorization": f"Bearer {google_user['token']}",
                   "Content-Type": "application/json"}
        # /billing/status must now show not allowed
        r = requests.get(f"{API}/billing/status", headers=headers, timeout=15)
        assert r.status_code == 200
        ent = r.json()
        assert ent["allowed"] is False, ent
        assert ent["plan"] in ("trial", "none"), ent

        # And chat POST must be 402
        sess = requests.post(f"{API}/sessions", json={"title": "TEST_paywall"},
                             headers=headers, timeout=15).json()
        sid = sess["id"]
        try:
            r2 = requests.post(
                f"{API}/sessions/{sid}/message",
                json={"text": "mag drop test"},
                headers=headers, timeout=30,
            )
            assert r2.status_code == 402, r2.text
        finally:
            requests.delete(f"{API}/sessions/{sid}", headers=headers, timeout=10)
    finally:
        # restore recent trial for downstream tests (harmless: session-scope cleanup deletes user)
        mongo.users.update_one(
            {"email": GOOGLE_EMAIL},
            {"$set": {"created_at": datetime.now(timezone.utc).isoformat()}},
        )


# --- Google user trial entitlement allows chat ------------------------------
def test_google_user_chat_allowed_during_trial(google_user, mongo):
    # ensure fresh created_at
    mongo.users.update_one(
        {"email": GOOGLE_EMAIL},
        {"$set": {"created_at": datetime.now(timezone.utc).isoformat()}},
    )
    headers = {"Authorization": f"Bearer {google_user['token']}",
               "Content-Type": "application/json"}
    sess = requests.post(f"{API}/sessions", json={"title": "TEST_google_trial"},
                         headers=headers, timeout=15).json()
    sid = sess["id"]
    try:
        # We only need to prove the request is ALLOWED (not 402). The stream may
        # be long; do a short streamed read to get the initial status/headers.
        with requests.post(
            f"{API}/sessions/{sid}/message",
            json={"text": "quick check"},
            headers=headers, stream=True, timeout=30,
        ) as r:
            assert r.status_code == 200, r.text
            # read a small chunk to confirm stream opened
            it = r.iter_content(chunk_size=64)
            _ = next(it, None)
    finally:
        requests.delete(f"{API}/sessions/{sid}", headers=headers, timeout=10)


# --- Regression: password login flows ---------------------------------------
def test_demo_password_login_still_works():
    r = requests.post(
        f"{API}/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    assert r.json()["user"]["email"] == DEMO_EMAIL


def test_password_login_for_google_user_returns_401_not_500(google_user):
    # google user has password_hash=None. verify_password must safely return False.
    r = requests.post(
        f"{API}/auth/login",
        json={"email": GOOGLE_EMAIL, "password": "anything"},
        timeout=15,
    )
    assert r.status_code == 401, r.text  # NOT 500
    assert "invalid" in (r.json().get("detail", "").lower())


def test_change_password_for_google_user_returns_400_not_500(google_user):
    r = requests.post(
        f"{API}/auth/change-password",
        json={"current_password": "anything", "new_password": "brandnew1"},
        headers={"Authorization": f"Bearer {google_user['token']}",
                 "Content-Type": "application/json"},
        timeout=15,
    )
    assert r.status_code == 400, r.text
    assert "incorrect" in (r.json().get("detail", "").lower())


def test_change_password_for_password_user_still_works():
    """Round-trip demo user password: change to X then back to original."""
    # login
    r = requests.post(
        f"{API}/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    headers = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

    tmp = "squawk456"
    r1 = requests.post(
        f"{API}/auth/change-password",
        json={"current_password": DEMO_PASSWORD, "new_password": tmp},
        headers=headers, timeout=15,
    )
    assert r1.status_code == 200, r1.text
    # verify new pw works
    r2 = requests.post(
        f"{API}/auth/login",
        json={"email": DEMO_EMAIL, "password": tmp},
        timeout=15,
    )
    assert r2.status_code == 200, r2.text
    # revert
    tok2 = r2.json()["token"]
    r3 = requests.post(
        f"{API}/auth/change-password",
        json={"current_password": tmp, "new_password": DEMO_PASSWORD},
        headers={"Authorization": f"Bearer {tok2}", "Content-Type": "application/json"},
        timeout=15,
    )
    assert r3.status_code == 200, r3.text
    # final sanity: original pw works again
    r4 = requests.post(
        f"{API}/auth/login",
        json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        timeout=15,
    )
    assert r4.status_code == 200, r4.text
