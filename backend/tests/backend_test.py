"""Squawk King IA - backend regression tests.

Covers: auth (login/register/me), aircraft CRUD, corpus, sessions, logbook,
PDF manual upload+extract, and SSE chat streaming with GPT-5.4.
"""
import io
import os
import re
import json
import time
import uuid
import requests
import pytest

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

DEMO_EMAIL = "mechanic@squawkking.io"
DEMO_PASSWORD = "squawk123"


# --- fixtures ---------------------------------------------------------------
@pytest.fixture(scope="session")
def s():
    ses = requests.Session()
    ses.headers.update({"Content-Type": "application/json"})
    return ses


@pytest.fixture(scope="session")
def token(s):
    r = s.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def auth(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# --- AUTH -------------------------------------------------------------------
def test_login_demo(s):
    r = s.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == DEMO_EMAIL
    assert body["token"]


def test_login_bad_password(s):
    r = s.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": "wrong"})
    assert r.status_code == 401


def test_register_new_user(s):
    email = f"test.{uuid.uuid4().hex[:8]}@example.com"
    r = s.post(f"{API}/auth/register", json={"email": email, "password": "pass1234", "name": "Test"})
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    me = s.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200
    assert me.json()["email"] == email


def test_me_requires_auth(s):
    r = s.get(f"{API}/auth/me")
    assert r.status_code == 401


# --- AIRCRAFT ---------------------------------------------------------------
def test_seeded_aircraft_present(s, auth):
    r = s.get(f"{API}/aircraft", headers=auth)
    assert r.status_code == 200
    items = r.json()
    tails = {a.get("tail_number") for a in items}
    assert "N172SK" in tails and "N28PA" in tails, tails


# --- CORPUS -----------------------------------------------------------------
def test_corpus_seeded_331(s, auth):
    # Updated 2026-08-25: corpus replaced with 331 real owner-authored logbook
    # records (was 12 hardcoded samples) — see backend/corpus_seed.py.
    r = s.get(f"{API}/corpus", headers=auth)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 331, f"expected 331 seeded, got {len(items)}"


def test_corpus_search(s, auth):
    r = s.get(f"{API}/corpus?q=magneto", headers=auth)
    assert r.status_code == 200
    assert len(r.json()) >= 1


# --- SESSIONS ---------------------------------------------------------------
def test_create_session_and_list(s, auth):
    r = s.post(f"{API}/sessions", json={"title": "TEST_session"}, headers=auth)
    assert r.status_code == 200
    sid = r.json()["id"]
    r2 = s.get(f"{API}/sessions", headers=auth)
    assert any(x["id"] == sid for x in r2.json())
    # cleanup
    s.delete(f"{API}/sessions/{sid}", headers=auth)


# --- LOGBOOK ----------------------------------------------------------------
def test_logbook_crud(s, auth):
    payload = {"date": "2026-01-01", "ata": "74-00", "description": "TEST_logbook entry"}
    r = s.post(f"{API}/logbook", json=payload, headers=auth)
    assert r.status_code == 200, r.text
    eid = r.json()["id"]
    lst = s.get(f"{API}/logbook", headers=auth).json()
    assert any(e["id"] == eid for e in lst)
    d = s.delete(f"{API}/logbook/{eid}", headers=auth)
    assert d.status_code == 200


# --- MANUAL UPLOAD (PDF extract) --------------------------------------------
def _tiny_pdf_bytes():
    """Build a valid tiny PDF with text 'MAGNETO TIMING CHECK ATA 74-00-00'."""
    # minimal PDF from scratch
    content_stream = (
        b"BT /F1 12 Tf 72 720 Td (MAGNETO TIMING CHECK ATA 74-00-00 SQUAWK) Tj ET"
    )
    pdf = b"%PDF-1.4\n"
    objs = []
    def add(obj_bytes):
        objs.append(obj_bytes)
        return len(objs)
    add(b"<< /Type /Catalog /Pages 2 0 R >>")
    add(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    add(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>")
    add(b"<< /Length " + str(len(content_stream)).encode() + b" >>\nstream\n" + content_stream + b"\nendstream")
    add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    xref_positions = []
    body = b""
    for i, o in enumerate(objs, start=1):
        xref_positions.append(len(pdf) + len(body))
        body += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    pdf += body
    xref_start = len(pdf)
    pdf += b"xref\n0 " + str(len(objs) + 1).encode() + b"\n"
    pdf += b"0000000000 65535 f \n"
    for pos in xref_positions:
        pdf += f"{pos:010d} 00000 n \n".encode()
    pdf += b"trailer << /Size " + str(len(objs) + 1).encode() + b" /Root 1 0 R >>\nstartxref\n"
    pdf += str(xref_start).encode() + b"\n%%EOF"
    return pdf


def test_manual_upload_and_extract(s, token, auth):
    # get an aircraft id
    ac = s.get(f"{API}/aircraft", headers=auth).json()
    assert ac
    aid = ac[0]["id"]
    pdf = _tiny_pdf_bytes()
    files = {"file": ("TEST_manual.pdf", pdf, "application/pdf")}
    data = {"aircraft_id": aid, "doc_name": "TEST_manual", "doc_type": "AMM",
            "ata": "74-00-00", "status": "current"}
    r = requests.post(f"{API}/manuals",
                      headers={"Authorization": f"Bearer {token}"},
                      files=files, data=data, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["page_count"] >= 1, f"pdf pages not extracted: {body}"
    mid = body["id"]
    # cleanup
    s.delete(f"{API}/manuals/{mid}", headers=auth)


# --- CHAT STREAM ------------------------------------------------------------
def test_chat_stream_mechanic_first(s, token, auth):
    # create session
    sess = s.post(f"{API}/sessions", json={"title": "TEST_chat"}, headers=auth).json()
    sid = sess["id"]
    try:
        with requests.post(
            f"{API}/sessions/{sid}/message",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"text": "Rough mag drop on runup, right magneto drops 250 RPM"},
            stream=True, timeout=120,
        ) as r:
            assert r.status_code == 200, r.text
            events = []
            deltas = ""
            start = time.time()
            for raw in r.iter_lines(decode_unicode=True):
                if raw is None:
                    continue
                if raw.startswith("data:"):
                    payload = raw[5:].strip()
                    try:
                        evt = json.loads(payload)
                    except Exception:
                        continue
                    events.append(evt.get("type"))
                    if evt.get("type") == "delta":
                        deltas += evt.get("content", "")
                    if evt.get("type") == "done":
                        break
                if time.time() - start > 90:
                    break
        assert "meta" in events, events
        assert "done" in events, events
        assert len(deltas) > 100, f"stream text too short ({len(deltas)}): {deltas!r}"
        # mechanic-first check: numbered steps or keyword
        assert re.search(r"\b(magneto|mag|ignition|spark|timing)\b", deltas, re.I), deltas[:400]
    finally:
        s.delete(f"{API}/sessions/{sid}", headers=auth)
