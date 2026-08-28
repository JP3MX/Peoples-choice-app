"""
E2E backend tests for the emailed password-reset (Resend) flow.

Covers:
- forgot-password returns generic message (no token/code) for known+unknown emails
- reset link is logged to backend logs when Resend key is a placeholder
- reset-password with valid matching token completes
- login with new password works, old password rejected
- token reuse -> 400
- rate limit: 4th request within window -> 429
- regression: change-password still works for signed-in user
"""
import os
import re
import time
import subprocess
import uuid
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
DEMO_EMAIL = os.environ["DEMO_EMAIL"]
DEMO_PASSWORD = os.environ["DEMO_PASSWORD"]


def _fresh_email():
    return f"TEST_reset_{uuid.uuid4().hex[:10]}@example.com"


def _tail_backend_logs():
    """Return concatenated backend supervisor logs."""
    out = ""
    for p in ("/var/log/supervisor/backend.out.log", "/var/log/supervisor/backend.err.log"):
        try:
            r = subprocess.run(["tail", "-n", "500", p], capture_output=True, text=True, timeout=5)
            out += r.stdout + "\n"
        except Exception:
            pass
    return out


def _extract_reset_token(email: str, timeout: float = 5.0) -> str:
    """Find the last logged reset link for `email` and extract its token query param."""
    deadline = time.time() + timeout
    pattern = re.compile(rf"reset link for {re.escape(email)}:\s*(\S+)", re.IGNORECASE)
    last_token = None
    while time.time() < deadline:
        logs = _tail_backend_logs()
        matches = pattern.findall(logs)
        if matches:
            last_link = matches[-1]
            m = re.search(r"[?&]token=([A-Za-z0-9_\-]+)", last_link)
            if m:
                last_token = m.group(1)
                return last_token
        time.sleep(0.5)
    return last_token


@pytest.fixture(scope="module")
def s():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


class TestForgotPassword:
    def test_forgot_known_email_generic(self, s):
        email = _fresh_email()
        # Register first
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "orig-pass-123", "name": "T Reset"})
        assert r.status_code == 200, r.text

        r = s.post(f"{API}/auth/forgot-password", json={"email": email, "origin_url": BASE_URL})
        assert r.status_code == 200, r.text
        data = r.json()
        # Generic response only — no token / no code
        assert "message" in data
        assert "reset link" in data["message"].lower()
        assert "token" not in data
        assert "code" not in data

    def test_forgot_unknown_email_same_generic(self, s):
        email = f"TEST_unknown_{uuid.uuid4().hex[:8]}@example.com"
        r = s.post(f"{API}/auth/forgot-password", json={"email": email, "origin_url": BASE_URL})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "message" in data
        assert "reset link" in data["message"].lower()
        assert "token" not in data
        assert "code" not in data

    def test_reset_flow_end_to_end_and_reuse_rejected(self, s):
        email = _fresh_email()
        old_pw = "orig-pass-123"
        new_pw = "brand-new-pw-456"
        # register
        r = s.post(f"{API}/auth/register", json={"email": email, "password": old_pw, "name": "Reset User"})
        assert r.status_code == 200, r.text

        # request reset
        r = s.post(f"{API}/auth/forgot-password", json={"email": email, "origin_url": BASE_URL})
        assert r.status_code == 200

        token = _extract_reset_token(email)
        assert token, "Reset token was not found in backend logs — expected because Resend key is a placeholder"

        # reset with valid token + matching password
        r = s.post(f"{API}/auth/reset-password", json={"token": token, "new_password": new_pw})
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # login with new password works
        r = s.post(f"{API}/auth/login", json={"email": email, "password": new_pw})
        assert r.status_code == 200, r.text
        assert "token" in r.json()

        # old password rejected
        r = s.post(f"{API}/auth/login", json={"email": email, "password": old_pw})
        assert r.status_code == 401

        # token reuse -> 400
        r = s.post(f"{API}/auth/reset-password", json={"token": token, "new_password": "another-pass-789"})
        assert r.status_code == 400
        assert "invalid" in r.json().get("detail", "").lower() or "already" in r.json().get("detail", "").lower()

    def test_reset_short_password_rejected(self, s):
        r = s.post(f"{API}/auth/reset-password", json={"token": "any", "new_password": "abc"})
        assert r.status_code == 400
        assert "6" in r.json().get("detail", "")

    def test_rate_limit_fourth_request_within_window_returns_429(self, s):
        email = _fresh_email()
        # No need to register — rate limiter runs before user lookup.
        for i in range(3):
            r = s.post(f"{API}/auth/forgot-password", json={"email": email, "origin_url": BASE_URL})
            assert r.status_code == 200, f"attempt {i+1} status {r.status_code}"
        r4 = s.post(f"{API}/auth/forgot-password", json={"email": email, "origin_url": BASE_URL})
        assert r4.status_code == 429, r4.text
        assert "too many" in r4.json().get("detail", "").lower()


class TestChangePasswordRegression:
    def test_change_password_still_works(self, s):
        email = _fresh_email()
        pw1 = "start-pass-1"
        pw2 = "new-pass-2"
        r = s.post(f"{API}/auth/register", json={"email": email, "password": pw1, "name": "CP User"})
        assert r.status_code == 200, r.text
        token = r.json()["token"]

        r = s.post(f"{API}/auth/change-password",
                   json={"current_password": pw1, "new_password": pw2},
                   headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200, r.text

        # login with new password
        r = s.post(f"{API}/auth/login", json={"email": email, "password": pw2})
        assert r.status_code == 200

        # login with old password fails
        r = s.post(f"{API}/auth/login", json={"email": email, "password": pw1})
        assert r.status_code == 401


class TestLoginRegistrationRegression:
    def test_demo_login(self, s):
        r = s.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data
        assert data["user"]["email"] == DEMO_EMAIL

    def test_register_new_user(self, s):
        email = _fresh_email()
        r = s.post(f"{API}/auth/register", json={"email": email, "password": "pw123456", "name": "Reg User"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "token" in data
        assert data["user"]["email"].lower() == email.lower()
